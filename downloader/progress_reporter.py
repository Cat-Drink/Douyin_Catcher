"""进度信号节流器模块。

缓存进度更新并按固定间隔（默认 500ms）批量发送，避免每个 64KB 数据块
都触发一次回调导致性能问题。严格遵循设计文档 5.5 节。

核心机制：
1. ``update()`` 调用时更新内部最新值字典（按 task_item_id 去重）
2. 专门的汇报协程每 ``flush_interval_ms`` 毫秒取字典全部值，批量调用回调
3. 回调为普通可调用对象，不依赖 Qt 信号（由后续 worker 里程碑桥接）
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass

from app.logger import get_logger

logger = get_logger(__name__)

# 默认刷新间隔 500ms（设计文档 5.5 节）
DEFAULT_FLUSH_INTERVAL_MS: int = 500


@dataclass(frozen=True)
class ProgressUpdate:
    """单条进度更新数据。

    Attributes:
        task_item_id: 任务项 ID
        downloaded_bytes: 已下载字节数
        total_bytes: 文件总字节数
        status: 任务项状态，默认 "downloading"
    """

    task_item_id: int
    downloaded_bytes: int
    total_bytes: int
    status: str = "downloading"


class ProgressReporter:
    """进度信号节流器。

    缓存进度更新，按固定间隔批量发送，避免高频回调。

    使用方式::

        reporter = ProgressReporter(on_progress=my_callback)
        reporter.start()
        # 下载过程中：
        reporter.update(item_id, 1024, 4096)
        reporter.update(item_id, 2048, 4096)
        # ... 500ms 后 on_progress 被调用，收到 [ProgressUpdate(item_id, 2048, 4096)]
        reporter.stop()
    """

    def __init__(
        self,
        on_progress: Callable[[list[ProgressUpdate]], None],
        flush_interval_ms: int = DEFAULT_FLUSH_INTERVAL_MS,
    ) -> None:
        """初始化进度节流器。

        Args:
            on_progress: 进度回调，接收批量 ProgressUpdate 列表
            flush_interval_ms: 刷新间隔毫秒数，默认 500ms
        """
        self._on_progress = on_progress
        self._flush_interval_ms = flush_interval_ms
        self._latest: dict[int, ProgressUpdate] = {}
        self._queue: asyncio.Queue[None] = asyncio.Queue()
        self._report_task: asyncio.Task[None] | None = None
        self._stopped = False

    def update(self, task_item_id: int, downloaded_bytes: int, total_bytes: int) -> None:
        """更新进度（不立即触发回调，缓存到内部字典）。

        同一 task_item_id 多次调用只保留最新值（Queue 去重）。

        Args:
            task_item_id: 任务项 ID
            downloaded_bytes: 已下载字节数
            total_bytes: 文件总字节数
        """
        self._latest[task_item_id] = ProgressUpdate(
            task_item_id=task_item_id,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
        )
        # 向 Queue 放入标记通知汇报协程有新数据
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)

    def flush(self) -> None:
        """强制发送当前积累的所有进度更新。

        从最新值字典取出全部，组装成 list，调用 on_progress 回调，然后清空字典。
        """
        if not self._latest:
            return
        updates = list(self._latest.values())
        self._latest.clear()
        try:
            self._on_progress(updates)
        except Exception:
            logger.exception("进度回调执行异常")

    def start(self) -> None:
        """启动汇报协程。"""
        if self._report_task is not None:
            return
        self._stopped = False
        self._report_task = asyncio.create_task(self._report_loop())
        logger.debug("进度汇报协程已启动，刷新间隔 %dms", self._flush_interval_ms)

    async def stop(self) -> None:
        """停止汇报协程，flush 残留进度。

        等待汇报协程退出后返回。
        """
        self._stopped = True
        # 唤醒可能阻塞在 Queue.get 的协程
        await self._queue.put(None)
        if self._report_task is not None:
            await self._report_task
            self._report_task = None
        # flush 残留进度
        self.flush()
        logger.debug("进度汇报协程已停止")

    async def _report_loop(self) -> None:
        """汇报协程主循环。

        每隔 ``flush_interval_ms`` 毫秒 flush 一次，收到停止信号时退出。
        """
        interval = self._flush_interval_ms / 1000.0
        while not self._stopped:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._queue.get(), timeout=interval)
            if self._stopped:
                break
            self.flush()
