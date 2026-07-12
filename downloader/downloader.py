"""单项下载器模块。

实现单个 ``TaskItem`` 的下载逻辑，包括 httpx Range 请求、流式写入、
失败重试、图集并发、取消处理。严格遵循设计文档 5.2 节（下载流程）
与 5.3 节（重试策略）。

下载流程（设计文档 5.2 节）：
1. 从 SQLite 取 task_item，置为 downloading
2. 检查 .part 文件 → 读取已下载字节数（断点续传）
3. httpx Range 请求
4. 流式接收 64KB 块 → 追加写入 .part → 每 5s/1MB 持久化 → 更新进度
5. 完成 → .part 重命名为最终文件 → status=completed

重试策略（设计文档 5.3 节）：
- 网络异常 / 5xx / 461 / 412 → 重试，2^retry_count 秒指数退避
- 3 次上限 → status=failed
- 4xx（非限流）→ 直接失败不重试
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.logger import get_logger
from app.models import TaskItem, now_iso
from app.repositories import TaskItemRepository, TaskRepository
from downloader.progress_reporter import ProgressReporter

logger = get_logger(__name__)

# === 常量（设计文档 5.2 / 5.3 节）===

# 流式接收块大小 64KB
CHUNK_SIZE: int = 64 * 1024

# 进度持久化间隔 5 秒
PERSIST_INTERVAL_SECONDS: int = 5

# 进度持久化间隔 1MB
PERSIST_INTERVAL_BYTES: int = 1024 * 1024

# 最大重试次数 3
MAX_RETRY_COUNT: int = 3

# 指数退避底数，等待 2^retry_count 秒
RETRY_BACKOFF_BASE: int = 2

# 风控限流状态码（与爬虫层一致，触发重试）
RATE_LIMITED_STATUS_CODES: frozenset[int] = frozenset({461, 412})


@dataclass(frozen=True)
class DownloadResult:
    """单项下载结果。

    Attributes:
        success: 是否下载成功
        local_path: 成功时的本地文件路径，失败为 None
        error: 失败原因，成功为 None
    """

    success: bool
    local_path: str | None = None
    error: str | None = None


class Downloader:
    """单项下载器。

    通过 httpx Range 请求流式下载文件，支持断点续传、失败重试、图集并发。
    进度通过 ProgressReporter 节流上报，状态持久化到 SQLite。

    注意：Downloader **不**修改 status 为 paused（归 Scheduler），
    仅在下载完成时置 completed、失败时置 failed。
    """

    def __init__(
        self,
        progress_reporter: ProgressReporter,
        http_client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        conn: sqlite3.Connection,
    ) -> None:
        """初始化下载器。

        Args:
            progress_reporter: 进度节流器
            http_client: httpx 异步客户端
            semaphore: 并发信号量（图集子任务也受此约束）
            conn: SQLite 连接（用于状态持久化与 download_dir 查询）
        """
        self._progress_reporter = progress_reporter
        self._http_client = http_client
        self._semaphore = semaphore
        self._conn = conn
        self._item_repo = TaskItemRepository(conn)
        self._task_repo = TaskRepository(conn)

    # === 路径推导 ===

    def _get_download_dir(self, task_item: TaskItem) -> Path:
        """查询 task_item 所属 task 的 download_dir。

        Args:
            task_item: 任务项

        Returns:
            下载目录 Path

        Raises:
            ValueError: task 不存在或 download_dir 为空
        """
        task = self._task_repo.get(task_item.task_id)
        if task is None or not task.download_dir:
            raise ValueError(f"task_id={task_item.task_id} 的 download_dir 为空或 task 不存在")
        return Path(task.download_dir)

    def _get_final_path(self, task_item: TaskItem, url: str, index: int | None = None) -> Path:
        """推导最终文件路径。

        - video / long_video: ``{download_dir}/{aweme_id}.{ext}``
        - image_set: ``{download_dir}/{aweme_id}/{aweme_id}_{index}.{ext}``

        Args:
            task_item: 任务项
            url: 下载直链（用于提取扩展名）
            index: 图集图片序号（从 1 开始），仅 image_set 使用

        Returns:
            最终文件路径
        """
        download_dir = self._get_download_dir(task_item)
        ext = self._extract_extension(url, task_item.type)
        aweme_id = task_item.aweme_id or f"item_{task_item.id}"
        if task_item.type == "image_set" and index is not None:
            target_dir = download_dir / aweme_id
            return target_dir / f"{aweme_id}_{index}{ext}"
        return download_dir / f"{aweme_id}{ext}"

    def _get_part_path(self, final_path: Path) -> Path:
        """推导 .part 临时文件路径。

        在最终文件名后追加 ``.part`` 后缀。

        Args:
            final_path: 最终文件路径

        Returns:
            .part 临时文件路径
        """
        return Path(str(final_path) + ".part")

    @staticmethod
    def _extract_extension(url: str, item_type: str) -> str:
        """从 URL 提取文件扩展名。

        从 URL path 部分提取扩展名，无法识别时按类型给默认值。

        Args:
            url: 下载直链
            item_type: 任务项类型

        Returns:
            文件扩展名（含点号，如 ``.mp4``）
        """
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix and len(suffix) <= 5:
            return suffix
        # 默认扩展名
        if item_type == "image_set":
            return ".jpg"
        return ".mp4"

    # === 状态持久化 ===

    def _persist_progress(
        self,
        task_item_id: int,
        downloaded_bytes: int,
        total_bytes: int,
    ) -> None:
        """持久化下载进度到 SQLite。

        更新 ``task_items.downloaded_bytes``、``total_bytes``、``updated_at``。

        Args:
            task_item_id: 任务项 ID
            downloaded_bytes: 已下载字节数
            total_bytes: 文件总字节数
        """
        self._item_repo.update_bytes(task_item_id, downloaded_bytes, total_bytes)

    def _mark_status(
        self,
        task_item_id: int,
        status: str,
        fail_reason: str | None = None,
        local_path: str | None = None,
    ) -> None:
        """更新 task_items 状态及关联字段。

        Args:
            task_item_id: 任务项 ID
            status: 新状态
            fail_reason: 失败原因（仅 failed 时使用）
            local_path: 本地文件路径（仅 completed 时使用）
        """
        now = now_iso()
        with self._conn:
            if fail_reason is not None and local_path is not None:
                self._conn.execute(
                    "UPDATE task_items SET status=?, fail_reason=?, "
                    "local_path=?, updated_at=? WHERE id=?",
                    (status, fail_reason, local_path, now, task_item_id),
                )
            elif fail_reason is not None:
                self._conn.execute(
                    "UPDATE task_items SET status=?, fail_reason=?, updated_at=? WHERE id=?",
                    (status, fail_reason, now, task_item_id),
                )
            elif local_path is not None:
                self._conn.execute(
                    "UPDATE task_items SET status=?, local_path=?, updated_at=? WHERE id=?",
                    (status, local_path, now, task_item_id),
                )
            else:
                self._conn.execute(
                    "UPDATE task_items SET status=?, updated_at=? WHERE id=?",
                    (status, now, task_item_id),
                )

    # === 重试判断 ===

    def _should_retry(self, status_code: int | None, exception: Exception | None) -> bool:
        """判断是否应重试（设计文档 5.3 节）。

        - 网络异常（httpx.HTTPError 子类）→ True
        - HTTP 5xx → True
        - HTTP 461 / 412（风控限流）→ True
        - HTTP 4xx（非 461/412）→ False
        - HTTP 200/206 → 不进入重试逻辑（调用方保证）

        Args:
            status_code: HTTP 状态码，网络异常时为 None
            exception: 捕获的异常，HTTP 状态码错误时为 None

        Returns:
            是否应重试
        """
        if exception is not None:
            # httpx 网络异常（ConnectError、ReadTimeout、PoolTimeout 等）
            return isinstance(exception, httpx.HTTPError)
        if status_code is not None:
            if 500 <= status_code <= 599:
                return True
            if status_code in RATE_LIMITED_STATUS_CODES:
                return True
            if 400 <= status_code <= 499:
                return False
        return False

    async def _retry_with_backoff(self, retry_count: int) -> None:
        """指数退避等待 ``2^retry_count`` 秒（2s/4s/8s）。

        Args:
            retry_count: 当前重试次数（从 1 开始）
        """
        wait_seconds = RETRY_BACKOFF_BASE**retry_count
        logger.info("等待 %d 秒后重试（第 %d 次）", wait_seconds, retry_count)
        await asyncio.sleep(wait_seconds)

    # === 文件操作 ===

    def _finalize_file(self, part_path: Path, final_path: Path) -> str:
        """将 .part 文件重命名为最终文件名。

        若最终文件已存在则先删除（覆盖旧文件）。

        Args:
            part_path: .part 临时文件路径
            final_path: 最终文件路径

        Returns:
            最终文件路径字符串
        """
        if final_path.exists():
            final_path.unlink()
        part_path.rename(final_path)
        return str(final_path)

    # === 下载主流程 ===

    async def download(self, task_item: TaskItem) -> DownloadResult:
        """单项下载主入口（设计文档 5.2 节）。

        根据 type 分发到单文件或图集下载流程。
        image_set 类型的 url 字段以换行符分隔多个图片 URL。

        Args:
            task_item: 待下载任务项

        Returns:
            下载结果
        """
        self._mark_status(task_item.id, "downloading")
        logger.info(
            "开始下载 task_item id=%s aweme_id=%s type=%s",
            task_item.id,
            task_item.aweme_id,
            task_item.type,
        )

        if task_item.type == "image_set":
            urls = [u.strip() for u in task_item.url.split("\n") if u.strip()]
            if not urls:
                self._mark_status(task_item.id, "failed", fail_reason="图集 URL 为空")
                return DownloadResult(success=False, error="图集 URL 为空")
            final_path = self._get_final_path(task_item, urls[0], index=1)
            target_dir = final_path.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            return await self._download_image_set(task_item, urls, target_dir)

        final_path = self._get_final_path(task_item, task_item.url)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        return await self._download_single_file(task_item, task_item.url, final_path)

    async def _download_single_file(
        self,
        task_item: TaskItem,
        url: str,
        final_path: Path,
        mark_status: bool = True,
    ) -> DownloadResult:
        """单文件下载（视频/长视频/图集单张）。

        含 Range 续传、流式写入、重试。受总 Semaphore 约束。

        Args:
            task_item: 任务项
            url: 下载直链
            final_path: 最终文件路径
            mark_status: 是否在完成/失败时标记 task_items 状态。
                图集子下载设为 False，由 _download_image_set 统一标记。

        Returns:
            下载结果
        """
        part_path = self._get_part_path(final_path)
        retry_count = task_item.retry_count

        async with self._semaphore:
            while True:
                # 检查 .part 文件是否存在 → 读取已下载字节数（断点续传）
                downloaded_bytes = part_path.stat().st_size if part_path.exists() else 0

                # 构造 Range 请求头
                headers: dict[str, str] = {}
                if downloaded_bytes > 0:
                    headers["Range"] = f"bytes={downloaded_bytes}-"

                try:
                    async with self._http_client.stream("GET", url, headers=headers) as response:
                        if response.status_code == 200:
                            # 服务端不支持 Range 或文件已变，从头下载
                            downloaded_bytes = 0
                        elif response.status_code == 206:
                            pass  # 续传成功
                        elif self._should_retry(response.status_code, None):
                            # 可重试错误（5xx / 461 / 412）
                            retry_count += 1
                            self._item_repo.update_retry(task_item.id, retry_count)
                            if retry_count > MAX_RETRY_COUNT:
                                reason = f"HTTP {response.status_code} 重试耗尽"
                                if mark_status:
                                    self._mark_status(task_item.id, "failed", fail_reason=reason)
                                return DownloadResult(success=False, error=reason)
                            logger.warning(
                                "HTTP %d，第 %d 次重试 task_item id=%s",
                                response.status_code,
                                retry_count,
                                task_item.id,
                            )
                            await self._retry_with_backoff(retry_count)
                            continue
                        else:
                            # 不可重试错误（4xx 非限流）
                            reason = f"HTTP {response.status_code}"
                            if mark_status:
                                self._mark_status(task_item.id, "failed", fail_reason=reason)
                            return DownloadResult(success=False, error=reason)

                        # 流式接收
                        content_length = int(response.headers.get("Content-Length", 0))
                        total_bytes = downloaded_bytes + content_length
                        downloaded_bytes = await self._stream_to_file(
                            response,
                            part_path,
                            task_item,
                            downloaded_bytes,
                            total_bytes,
                        )

                    # 下载完成 → 重命名 → 标记完成
                    final_str = self._finalize_file(part_path, final_path)
                    if mark_status:
                        self._mark_status(task_item.id, "completed", local_path=final_str)
                    logger.info("下载完成 task_item id=%s path=%s", task_item.id, final_str)
                    return DownloadResult(success=True, local_path=final_str)

                except asyncio.CancelledError:
                    # 暂停/取消：持久化进度，保留 .part 文件，不修改 status（归 Scheduler）
                    # _stream_to_file 可能已持久化更准确的值，此处读 .part 实际大小兜底
                    actual_bytes = part_path.stat().st_size if part_path.exists() else 0
                    total = total_bytes if "total_bytes" in locals() else 0
                    self._persist_progress(task_item.id, actual_bytes, total)
                    logger.info(
                        "下载被取消 task_item id=%s 已保存进度 %d bytes",
                        task_item.id,
                        actual_bytes,
                    )
                    raise

                except httpx.HTTPError as e:
                    # 网络异常 → 重试
                    retry_count += 1
                    self._item_repo.update_retry(task_item.id, retry_count)
                    if retry_count > MAX_RETRY_COUNT:
                        reason = f"网络异常重试耗尽: {e}"
                        if mark_status:
                            self._mark_status(task_item.id, "failed", fail_reason=reason)
                        return DownloadResult(success=False, error=reason)
                    logger.warning(
                        "网络异常 %s，第 %d 次重试 task_item id=%s",
                        e,
                        retry_count,
                        task_item.id,
                    )
                    await self._retry_with_backoff(retry_count)
                    continue

    async def _stream_to_file(
        self,
        response: httpx.Response,
        part_path: Path,
        task_item: TaskItem,
        downloaded_bytes: int,
        total_bytes: int,
    ) -> int:
        """流式接收响应体写入 .part 文件。

        每块 64KB 追加写入、更新内存计数、每 5s/1MB 持久化、更新 ProgressReporter。
        捕获 CancelledError 时持久化进度后重抛。

        Args:
            response: httpx 流式响应
            part_path: .part 临时文件路径
            task_item: 任务项
            downloaded_bytes: 起始已下载字节数（断点续传）
            total_bytes: 文件总字节数

        Returns:
            最终已下载字节数
        """
        last_persist_time = time.monotonic()
        last_persist_bytes = downloaded_bytes
        # downloaded_bytes == 0 表示从头下载（新文件或服务端返回 200 不支持 Range）
        # → 用 "wb" 截断旧 .part 内容；否则 "ab" 续传追加。
        mode = "wb" if downloaded_bytes == 0 else "ab"

        try:
            with open(part_path, mode) as f:
                async for chunk in response.aiter_bytes(CHUNK_SIZE):
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    # 更新进度（节流器内部去重）
                    self._progress_reporter.update(
                        task_item.id,
                        downloaded_bytes,
                        total_bytes,
                    )
                    # 检查持久化条件：5 秒 或 1MB
                    now = time.monotonic()
                    if (
                        now - last_persist_time >= PERSIST_INTERVAL_SECONDS
                        or downloaded_bytes - last_persist_bytes >= PERSIST_INTERVAL_BYTES
                    ):
                        self._persist_progress(task_item.id, downloaded_bytes, total_bytes)
                        last_persist_time = now
                        last_persist_bytes = downloaded_bytes
        except asyncio.CancelledError:
            # 持久化进度后重抛（设计文档 5.4 节）
            self._persist_progress(task_item.id, downloaded_bytes, total_bytes)
            raise

        # 最终持久化一次
        self._persist_progress(task_item.id, downloaded_bytes, total_bytes)
        return downloaded_bytes

    async def _download_image_set(
        self,
        task_item: TaskItem,
        urls: list[str],
        target_dir: Path,
    ) -> DownloadResult:
        """图集并发下载（设计文档 5.2 节 + 2.4 节）。

        对每个 URL 创建 _download_single_file 子任务，asyncio.gather 并发执行。
        每个子任务受总 Semaphore 约束。任一失败 → 整个图集标记 failed。

        Args:
            task_item: 任务项
            urls: 图片直链列表
            target_dir: 图集目标目录

        Returns:
            下载结果（成功时 local_path 为目录路径）
        """
        logger.info(
            "图集下载 task_item id=%s 共 %d 张图片",
            task_item.id,
            len(urls),
        )
        tasks: list = []
        for i, url in enumerate(urls, 1):
            final_path = self._get_final_path(task_item, url, index=i)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(self._download_single_file(task_item, url, final_path, mark_status=False))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查结果：任一失败 → 整个图集失败
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                if not isinstance(result, asyncio.CancelledError):
                    reason = f"图片 {i + 1} 下载异常: {result}"
                    self._mark_status(task_item.id, "failed", fail_reason=reason)
                    return DownloadResult(success=False, error=reason)
                raise result
            if not result.success:
                reason = f"图片 {i + 1} 下载失败: {result.error}"
                self._mark_status(task_item.id, "failed", fail_reason=reason)
                return DownloadResult(success=False, error=reason)

        # 全部成功
        self._mark_status(task_item.id, "completed", local_path=str(target_dir))
        logger.info("图集下载完成 task_item id=%s path=%s", task_item.id, target_dir)
        return DownloadResult(success=True, local_path=str(target_dir))
