"""异步工作线程模块。

在 ``QThread`` 后台线程中创建并运行 ``asyncio`` 事件循环，
UI 线程通过 ``submit()`` 调度协程到工作线程执行，支持优雅关闭。

严格遵循设计文档 2.3 节（线程模型）与 v0.0.6 计划文档任务 1。

线程模型：
    - Qt 主线程跑 UI
    - 后台工作线程跑 asyncio 事件循环
    - 二者通过 Qt 信号/槽线程安全通信
    - UI 线程通过 ``submit(coro)`` 把协程调度到工作线程的 loop 中执行

优雅关闭流程（``stop()``）：
    1. 通过 ``loop.call_soon_threadsafe`` 设置停止信号
    2. ``run()`` 中的 ``run_until_complete`` 返回
    3. ``_cleanup()`` 取消所有未完成的 task
    4. ``loop.stop()`` 停止 loop
    5. 等待 QThread 退出（超时 10 秒强制 terminate）
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import threading
from collections.abc import Awaitable, Coroutine

from PySide6.QtCore import QThread

from app.logger import get_logger

logger = get_logger(__name__)

# 等待 loop 就绪的超时秒数
LOOP_READY_TIMEOUT: float = 5.0

# stop() 等待线程退出的超时秒数
STOP_TIMEOUT: int = 10


class AsyncWorker(QThread):
    """后台工作线程，承载 asyncio 事件循环。

    UI 线程通过 ``submit()`` 把协程调度到工作线程的 loop 中执行；
    工作线程内部通过 ``run_in_thread()`` 提交协程。
    ``stop()`` 时取消所有未完成任务并优雅退出。

    使用方式::

        worker = AsyncWorker()
        worker.start()                    # 启动后台线程 + loop
        future = worker.submit(coro)      # UI 线程提交协程
        result = future.result(timeout=5) # 同步等待结果
        worker.stop()                     # 优雅关闭
    """

    def __init__(self, parent=None) -> None:
        """初始化异步工作线程。

        Args:
            parent: Qt 父对象（可选）
        """
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        # 用于等待 loop 在工作线程中创建完成（跨线程同步）
        self._loop_ready: threading.Event = threading.Event()
        # loop 内的停止信号
        self._stop_event: asyncio.Event | None = None
        # 工作线程的线程 ID（run() 中赋值）
        self._thread_id: int | None = None

    def run(self) -> None:
        """QThread.run 重写：在工作线程创建并运行 asyncio loop。

        流程：
            1. 创建 ``asyncio.new_event_loop()``，设为当前线程的 loop
            2. ``_loop_ready.set()`` 通知 UI 线程 loop 已就绪
            3. 创建 ``asyncio.Event`` 作为停止信号
            4. ``run_until_complete(stop_event.wait())`` 阻塞运行 loop
            5. 退出前调用 ``_cleanup()`` 清理
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._thread_id = threading.get_ident()
        self._stop_event = asyncio.Event()
        self._loop_ready.set()
        logger.info("AsyncWorker loop 已在工作线程创建")

        try:
            self._loop.run_until_complete(self._stop_event.wait())
        except Exception:
            logger.exception("AsyncWorker loop 运行异常")
        finally:
            # 在 loop 关闭前清理未完成的 task
            if self._loop.is_running():
                self._loop.run_until_complete(self._cleanup())
            else:
                # loop 已停止（如 stop() 中 call_soon_threadsafe 后），
                # 需要重新运行 _cleanup
                with contextlib.suppress(RuntimeError):
                    self._loop.run_until_complete(self._cleanup())
            self._loop.close()
            logger.info("AsyncWorker loop 已关闭")

    def start(self) -> None:
        """启动线程并等待 loop 就绪。

        重写 ``QThread.start``，在调用 ``super().start()`` 后阻塞等待
        loop 在工作线程中创建完成（超时 ``LOOP_READY_TIMEOUT`` 秒抛 ``RuntimeError``）。

        Raises:
            RuntimeError: loop 启动超时
        """
        super().start()
        if not self._loop_ready.wait(timeout=LOOP_READY_TIMEOUT):
            raise RuntimeError("AsyncWorker loop start timeout")
        logger.info("AsyncWorker 已启动，loop 就绪")

    def stop(self) -> None:
        """优雅关闭：设置停止信号，取消未完成任务，等待线程退出。

        流程：
            1. 若 loop 或 stop_event 为 None → 直接 return（未启动）
            2. ``call_soon_threadsafe`` 设置停止信号
            3. ``wait(STOP_TIMEOUT)`` 等待线程退出
            4. 超时则 ``terminate()`` 强制终止（最后手段）
        """
        if self._loop is None or self._stop_event is None:
            return
        if not self.isRunning():
            return

        # 在工作线程的 loop 中设置停止信号
        self._loop.call_soon_threadsafe(self._stop_event.set)

        # 等待线程退出
        if not self.wait(STOP_TIMEOUT * 1000):
            logger.warning("AsyncWorker stop 超时，强制 terminate")
            self.terminate()
            self.wait(STOP_TIMEOUT * 1000)

        self._loop_ready.clear()
        logger.info("AsyncWorker 已停止")

    def submit(self, coro: Coroutine) -> concurrent.futures.Future:
        """UI 线程提交协程到工作线程的 loop 执行。

        通过 ``asyncio.run_coroutine_threadsafe`` 线程安全地调度协程。
        任务跟踪由 ``_cleanup`` 中的 ``asyncio.all_tasks`` 统一处理。

        Args:
            coro: 待执行的协程

        Returns:
            ``concurrent.futures.Future``，可在 UI 线程同步等待结果或添加回调

        Raises:
            RuntimeError: loop 未就绪
        """
        if self._loop is None:
            raise RuntimeError("AsyncWorker loop 未就绪，请先 start()")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(self._log_future_exception)
        logger.debug("已提交协程到工作线程")
        return future

    @staticmethod
    def _log_future_exception(future: concurrent.futures.Future) -> None:
        """Future 完成回调：记录未捕获的异常。

        防止 ``submit`` 提交的协程异常被静默吞掉。
        """
        exc = future.exception()
        if exc is not None:
            logger.error("工作线程协程未捕获异常: %s", exc, exc_info=exc)

    def run_in_thread(self, coro: Coroutine) -> Awaitable:
        """工作线程内部提交协程。

        断言当前线程为工作线程，用 ``loop.create_task`` 创建 Task。

        Args:
            coro: 待执行的协程

        Returns:
            ``asyncio.Task``（Awaitable），可在工作线程内 await

        Raises:
            RuntimeError: 在非工作线程调用
        """
        if self._thread_id is None or threading.get_ident() != self._thread_id:
            raise RuntimeError("run_in_thread 只能在工作线程内部调用")
        if self._loop is None:
            raise RuntimeError("AsyncWorker loop 未就绪")
        task = self._loop.create_task(coro)
        logger.debug("已在工作线程内部创建 Task")
        return task

    async def _cleanup(self) -> None:
        """loop 退出前清理：取消所有未完成的 task。

        使用 ``asyncio.all_tasks`` 获取当前 loop 的全部未完成 task，
        逐个取消并等待取消完成。在 ``run()`` 的 finally 块中调用。
        """
        # 获取当前 loop 的全部 task，排除自身（_cleanup 本身也是 task）
        current = asyncio.current_task()
        tasks = {t for t in asyncio.all_tasks(self._loop) if t is not current}
        if not tasks:
            return

        logger.info("清理 %d 个未完成的 task", len(tasks))
        for task in tasks:
            if not task.done():
                task.cancel()
        # 等待所有取消完成
        await asyncio.gather(*tasks, return_exceptions=True)
