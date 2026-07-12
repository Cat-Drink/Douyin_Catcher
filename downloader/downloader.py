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
