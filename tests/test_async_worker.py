"""AsyncWorker 单元测试。

覆盖启动/停止、submit 协程调度、run_in_thread、优雅关闭等场景。
使用真实 AsyncWorker（真实后台线程 + asyncio loop），测试结束 stop() 清理。

注意：测试需要 QApplication 实例（由 qapp fixture 提供），
因为 AsyncWorker 继承自 QThread，需要 Qt 事件循环。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import threading
import time

import pytest

from worker.async_worker import LOOP_READY_TIMEOUT, STOP_TIMEOUT, AsyncWorker

# ==================== 常量测试 ====================


class TestConstants:
    """模块级常量契约测试。"""

    def test_loop_ready_timeout_5s(self) -> None:
        assert LOOP_READY_TIMEOUT == 5.0

    def test_stop_timeout_10s(self) -> None:
        assert STOP_TIMEOUT == 10


# ==================== 启动与停止测试 ====================


class TestStartStop:
    """AsyncWorker 启动与停止生命周期测试。"""

    def test_start_creates_loop(self, qapp, async_worker: AsyncWorker) -> None:
        """start() 后 _loop 不为 None。"""
        assert async_worker._loop is not None

    def test_start_loop_in_worker_thread(self, qapp, async_worker: AsyncWorker) -> None:
        """loop 所在线程不是主线程。"""
        main_thread_id = threading.get_ident()
        assert async_worker._thread_id is not None
        assert async_worker._thread_id != main_thread_id

    def test_start_sets_loop_ready(self, qapp, async_worker: AsyncWorker) -> None:
        """start() 返回时 loop_ready 已 set。"""
        assert async_worker._loop_ready.is_set()

    def test_stop_graceful_shutdown(self, qapp) -> None:
        """stop() 后线程退出（isRunning 为 False）。"""
        worker = AsyncWorker()
        worker.start()
        worker.stop()
        assert worker.isRunning() is False

    def test_stop_without_start_noop(self, qapp) -> None:
        """未 start 直接 stop 不报错。"""
        worker = AsyncWorker()
        worker.stop()  # 不应抛异常

    def test_stop_idempotent(self, qapp) -> None:
        """多次调用 stop() 不报错。"""
        worker = AsyncWorker()
        worker.start()
        worker.stop()
        worker.stop()  # 重复 stop 不报错

    def test_stop_clears_loop_ready(self, qapp) -> None:
        """stop() 后 loop_ready 被 clear。"""
        worker = AsyncWorker()
        worker.start()
        assert worker._loop_ready.is_set()
        worker.stop()
        assert worker._loop_ready.is_set() is False


# ==================== submit 协程测试 ====================


class TestSubmit:
    """submit 协程调度测试。"""

    def test_submit_returns_future(self, qapp, async_worker: AsyncWorker) -> None:
        """submit(coro) 返回 concurrent.futures.Future。"""

        async def simple_coro() -> int:
            return 42

        future = async_worker.submit(simple_coro())
        assert isinstance(future, concurrent.futures.Future)
        result = future.result(timeout=5)
        assert result == 42

    def test_submit_executes_in_worker_thread(self, qapp, async_worker: AsyncWorker) -> None:
        """submit 的协程在工作线程中执行。"""
        main_thread_id = threading.get_ident()
        worker_thread_id_holder: dict[str, int] = {}

        async def get_thread_id() -> int:
            worker_thread_id_holder["tid"] = threading.get_ident()
            return threading.get_ident()

        future = async_worker.submit(get_thread_id())
        result = future.result(timeout=5)
        assert result != main_thread_id
        assert worker_thread_id_holder["tid"] == async_worker._thread_id

    def test_submit_result_retrievable(self, qapp, async_worker: AsyncWorker) -> None:
        """future.result(timeout) 能拿到协程返回值。"""

        async def compute() -> str:
            await asyncio.sleep(0.01)
            return "hello"

        future = async_worker.submit(compute())
        assert future.result(timeout=5) == "hello"

    def test_submit_exception_propagated(self, qapp, async_worker: AsyncWorker) -> None:
        """协程抛异常时 future.result() 抛出该异常。"""

        async def fail() -> None:
            raise ValueError("test error")

        future = async_worker.submit(fail())
        with pytest.raises(ValueError, match="test error"):
            future.result(timeout=5)

    def test_submit_without_start_raises(self, qapp) -> None:
        """未 start 时 submit 抛 RuntimeError。"""
        worker = AsyncWorker()

        async def coro() -> None:
            pass

        with pytest.raises(RuntimeError, match="loop 未就绪"):
            worker.submit(coro())


# ==================== run_in_thread 测试 ====================


class TestRunInThread:
    """run_in_thread 工作线程内部提交测试。"""

    def test_run_in_thread_from_worker_thread(self, qapp, async_worker: AsyncWorker) -> None:
        """在工作线程内部调用 run_in_thread 创建 Task 并 await 成功。"""

        async def inner_coro() -> str:
            return "inner_result"

        async def outer_coro() -> str:
            task = async_worker.run_in_thread(inner_coro())
            return await task

        future = async_worker.submit(outer_coro())
        assert future.result(timeout=5) == "inner_result"

    def test_run_in_thread_from_ui_thread_raises(self, qapp, async_worker: AsyncWorker) -> None:
        """在 UI 线程调用 run_in_thread 抛 RuntimeError。"""

        async def dummy() -> None:
            pass

        with pytest.raises(RuntimeError, match="只能在工作线程内部调用"):
            async_worker.run_in_thread(dummy())


# ==================== 优雅关闭测试 ====================


class TestGracefulShutdown:
    """优雅关闭与任务取消测试。"""

    def test_stop_cancels_pending_tasks(self, qapp) -> None:
        """stop 时有未完成 task，task 被取消。"""
        worker = AsyncWorker()
        worker.start()

        cancel_caught: dict[str, bool] = {}

        async def long_running() -> None:
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancel_caught["cancelled"] = True
                raise

        future = worker.submit(long_running())
        time.sleep(0.2)  # 等待协程开始执行

        worker.stop()

        # future 应该以 CancelledError 完成
        try:
            future.result(timeout=5)
        except (asyncio.CancelledError, concurrent.futures.CancelledError):
            pass
        except Exception:
            pass

        assert cancel_caught.get("cancelled") is True

    def test_stop_with_multiple_pending_tasks(self, qapp) -> None:
        """stop 时多个未完成 task 全部被取消。"""
        worker = AsyncWorker()
        worker.start()

        cancel_count = {"count": 0}

        async def tracked_task() -> None:
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancel_count["count"] += 1
                raise

        f1 = worker.submit(tracked_task())
        f2 = worker.submit(tracked_task())
        f3 = worker.submit(tracked_task())
        time.sleep(0.3)  # 等待协程开始执行

        worker.stop()

        # 等待 futures 完成
        for f in [f1, f2, f3]:
            with contextlib.suppress(Exception):
                f.result(timeout=5)

        assert cancel_count["count"] == 3

    def test_stop_after_all_tasks_completed(self, qapp) -> None:
        """所有 task 完成后 stop 正常退出。"""
        worker = AsyncWorker()
        worker.start()

        async def quick_task() -> int:
            await asyncio.sleep(0.05)
            return 1

        f1 = worker.submit(quick_task())
        f2 = worker.submit(quick_task())
        f1.result(timeout=5)
        f2.result(timeout=5)

        worker.stop()
        assert worker.isRunning() is False

    def test_restart_after_stop(self, qapp) -> None:
        """stop 后可以重新 start。"""
        worker = AsyncWorker()
        worker.start()

        async def quick() -> int:
            return 42

        assert worker.submit(quick()).result(timeout=5) == 42
        worker.stop()

        worker.start()
        assert worker.submit(quick()).result(timeout=5) == 42
        worker.stop()
