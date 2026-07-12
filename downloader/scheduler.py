"""任务调度器模块。

实现并发控制、队列管理、暂停/恢复、去重、与进度节流器集成。
严格遵循设计文档 5.1 节（组件结构）、5.4 节（暂停/恢复）、2.4 节（并发控制）。

职责边界（设计文档 5.6 节 + 8.2 节）：
- Scheduler 负责队列管理、暂停/恢复、去重、回调触发
- Scheduler **不**直接处理 HTTP 下载（归 Downloader）
- 并发信号量由 Scheduler 创建并注入 Downloader，Downloader 在 _download_single_file
  内部 acquire/release；Scheduler 的 _run_download 不重复 acquire
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable

import httpx

from app.logger import get_logger
from app.models import TaskItem
from app.repositories import TaskItemRepository
from downloader.downloader import Downloader
from downloader.progress_reporter import ProgressReporter, ProgressUpdate

logger = get_logger(__name__)

# === 常量（设计文档 2.4 节）===

# 默认并发数 3
DEFAULT_MAX_CONCURRENT: int = 3

# 并发上限 10
MAX_CONCURRENT_LIMIT: int = 10


class Scheduler:
    """任务调度器。

    管理待下载队列，创建 asyncio.Task 执行下载，提供暂停/恢复/去重能力。
    通过回调函数通知外部（不直接依赖 Qt），由后续 ``worker/`` 里程碑桥接到 Qt 信号。

    并发控制通过 ``asyncio.Semaphore`` 实现，信号量由 Scheduler 创建并注入 Downloader。
    Downloader 在 ``_download_single_file`` 内部 acquire/release 信号量，
    图集子下载也受同一信号量约束（设计文档 2.4 节）。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        http_client: httpx.AsyncClient | None = None,
        on_item_completed: Callable[[int], None] | None = None,
        on_item_failed: Callable[[int, str], None] | None = None,
        on_progress: Callable[[list[ProgressUpdate]], None] | None = None,
    ) -> None:
        """初始化调度器。

        Args:
            conn: SQLite 连接（用于状态查询与更新）
            max_concurrent: 最大并发数，clamp 到 [1, 10]
            http_client: httpx 异步客户端；为 None 时内部创建
            on_item_completed: 下载成功回调，参数 task_item_id
            on_item_failed: 下载失败回调，参数 (task_item_id, fail_reason)
            on_progress: 进度批量回调，参数 list[ProgressUpdate]
        """
        self._conn = conn
        self._item_repo = TaskItemRepository(conn)
        self._on_item_completed = on_item_completed
        self._on_item_failed = on_item_failed

        # clamp 并发数到 [1, 10]
        self._max_concurrent = max(1, min(max_concurrent, MAX_CONCURRENT_LIMIT))
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

        # httpx 客户端：外部注入或内部创建
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None

        # ProgressReporter 与 Downloader
        self._progress_reporter = ProgressReporter(
            on_progress=on_progress or (lambda updates: None),
        )
        self._downloader = Downloader(
            progress_reporter=self._progress_reporter,
            http_client=self._http_client,
            semaphore=self._semaphore,
            conn=conn,
        )

        # 内部状态
        self._queue: asyncio.Queue[TaskItem | None] = asyncio.Queue()
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._running = False

    # === 生命周期 ===

    async def start(self) -> None:
        """启动调度循环与 ProgressReporter 汇报协程。"""
        if self._running:
            return
        self._running = True
        self._progress_reporter.start()
        self._loop_task = asyncio.create_task(self._schedule_loop())
        logger.info("调度器已启动，并发数=%d", self._max_concurrent)

    async def stop(self) -> None:
        """停止调度，等待进行中任务完成或取消，停止 ProgressReporter。"""
        if not self._running:
            return
        self._running = False
        # 向队列放入哨兵值停止调度循环
        await self._queue.put(None)
        if self._loop_task is not None:
            await self._loop_task
            self._loop_task = None
        # 取消所有进行中的下载任务
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        # 停止进度汇报
        self._progress_reporter.stop()
        # 关闭内部创建的 httpx 客户端
        if self._owns_http_client:
            await self._http_client.aclose()
        logger.info("调度器已停止")

    # === 队列管理 ===

    def add_task_items(self, items: list[TaskItem]) -> None:
        """添加待下载项到内部队列。

        入队前执行去重检查：已存在 ``completed`` 记录的 aweme_id 跳过（设计文档 5.6 节）。

        Args:
            items: 待下载任务项列表
        """
        for item in items:
            if item.aweme_id is not None and self._is_already_completed(item.aweme_id):
                logger.info("跳过已完成项 aweme_id=%s", item.aweme_id)
                continue
            self._queue.put_nowait(item)
            logger.info("入队 task_item id=%s aweme_id=%s", item.id, item.aweme_id)

    def _is_already_completed(self, aweme_id: str) -> bool:
        """去重：查 task_items 是否已有该 aweme_id 的 completed 记录。

        Args:
            aweme_id: 抖音作品 ID

        Returns:
            已存在 completed 记录返回 True
        """
        item = self._item_repo.get_by_aweme_id(aweme_id)
        return item is not None and item.status == "completed"

    # === 调度循环 ===

    async def _schedule_loop(self) -> None:
        """调度主循环：从队列取任务项，创建 asyncio.Task 执行下载。"""
        while self._running:
            task_item = await self._queue.get()
            if task_item is None:
                # 哨兵值：stop() 发出的停止信号
                break
            if task_item.id is None:
                logger.warning("task_item id 为 None，跳过")
                continue
            task = asyncio.create_task(self._run_download(task_item))
            self._tasks[task_item.id] = task
            task.add_done_callback(lambda t, tid=task_item.id: self._tasks.pop(tid, None))

    async def _run_download(self, task_item: TaskItem) -> None:
        """单个任务项下载执行器。

        调用 ``downloader.download()``，根据结果触发回调。
        信号量由 Downloader 内部 acquire/release，此处不重复。

        Args:
            task_item: 待下载任务项
        """
        try:
            result = await self._downloader.download(task_item)
            if result.success:
                logger.info("task_item id=%s 下载成功", task_item.id)
                if self._on_item_completed is not None:
                    self._on_item_completed(task_item.id)
            else:
                reason = result.error or "未知错误"
                logger.warning("task_item id=%s 下载失败: %s", task_item.id, reason)
                if self._on_item_failed is not None:
                    self._on_item_failed(task_item.id, reason)
        except asyncio.CancelledError:
            # 由 pause() 触发的取消，status 已由 pause() 设置为 paused
            logger.info("task_item id=%s 下载被取消（暂停）", task_item.id)
            raise
        except Exception as e:
            logger.exception("task_item id=%s 下载异常", task_item.id)
            self._item_repo.update_status(task_item.id, "failed", fail_reason=str(e))
            if self._on_item_failed is not None:
                self._on_item_failed(task_item.id, str(e))

    # === 并发数动态调整 ===

    def set_max_concurrent(self, max_concurrent: int) -> None:
        """动态调整并发数。

        clamp 到 [1, 10]，重建 Semaphore。已运行的下载不受影响（它们持有旧 Semaphore）。

        Args:
            max_concurrent: 新的最大并发数
        """
        new_value = max(1, min(max_concurrent, MAX_CONCURRENT_LIMIT))
        if new_value == self._max_concurrent:
            return
        self._max_concurrent = new_value
        self._semaphore = asyncio.Semaphore(new_value)
        self._downloader._semaphore = self._semaphore
        logger.info("并发数调整为 %d", new_value)
