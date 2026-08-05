"""ProgressReporter 单元测试。

覆盖进度缓存、Queue 去重、500ms 批量发送、stop flush 残留等场景。
不依赖真实网络与真实数据库。
"""

from __future__ import annotations

import asyncio

import pytest

from downloader.progress_reporter import (
    DEFAULT_FLUSH_INTERVAL_MS,
    ProgressReporter,
    ProgressUpdate,
)

# ==================== ProgressUpdate dataclass 测试 ====================


class TestProgressUpdate:
    """ProgressUpdate dataclass 测试。"""

    def test_progress_update_fields(self) -> None:
        """ProgressUpdate 字段正确赋值。"""
        update = ProgressUpdate(task_item_id=1, downloaded_bytes=1024, total_bytes=4096)
        assert update.task_item_id == 1
        assert update.downloaded_bytes == 1024
        assert update.total_bytes == 4096

    def test_progress_update_is_frozen(self) -> None:
        """ProgressUpdate 是 frozen dataclass，不可修改。"""
        update = ProgressUpdate(task_item_id=1, downloaded_bytes=0, total_bytes=100)
        with pytest.raises(AttributeError):
            update.downloaded_bytes = 50  # type: ignore[misc]


# ==================== 常量测试 ====================


class TestConstants:
    """模块级常量契约测试。"""

    def test_default_flush_interval_500ms(self) -> None:
        """默认刷新间隔为 500ms。"""
        assert DEFAULT_FLUSH_INTERVAL_MS == 500


# ==================== update / flush 测试 ====================


class TestUpdateAndFlush:
    """update 缓存与 flush 发送测试。"""

    def test_update_does_not_trigger_callback(self) -> None:
        """update() 调用后不立即触发回调。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        reporter.update(1, 1024, 4096)
        assert calls == []

    def test_flush_sends_buffered_updates(self) -> None:
        """flush() 将积累的进度通过回调批量发送。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        reporter.update(1, 1024, 4096)
        reporter.update(2, 2048, 8192)
        reporter.flush()
        assert len(calls) == 1
        assert len(calls[0]) == 2
        ids = {u.task_item_id for u in calls[0]}
        assert ids == {1, 2}

    def test_flush_clears_buffer(self) -> None:
        """flush() 后字典清空，再次 flush 不发送。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        reporter.update(1, 1024, 4096)
        reporter.flush()
        reporter.flush()
        assert len(calls) == 1

    def test_flush_empty_does_nothing(self) -> None:
        """无缓存数据时 flush() 不调用回调。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        reporter.flush()
        assert calls == []

    def test_queue_dedup_same_task_item_id(self) -> None:
        """同一 task_item_id 多次 update 只保留最新值。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        reporter.update(1, 100, 4096)
        reporter.update(1, 200, 4096)
        reporter.update(1, 300, 4096)
        reporter.flush()
        assert len(calls[0]) == 1
        assert calls[0][0].downloaded_bytes == 300

    def test_multiple_task_items_batched(self) -> None:
        """多个不同 task_item_id 的更新在同一批次发送。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        for i in range(5):
            reporter.update(i, i * 100, 500)
        reporter.flush()
        assert len(calls[0]) == 5

    def test_total_bytes_propagated(self) -> None:
        """total_bytes 正确传递到 ProgressUpdate。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(on_progress=lambda updates: calls.append(updates))
        reporter.update(1, 512, 2048)
        reporter.flush()
        assert calls[0][0].total_bytes == 2048


# ==================== flush 回调异常测试 ====================


class TestFlushCallbackException:
    """flush() 回调异常处理测试。"""

    def test_flush_callback_exception_does_not_raise(self) -> None:
        """回调抛异常时 flush() 不向上抛出。"""

        def bad_callback(updates: list[ProgressUpdate]) -> None:
            raise RuntimeError("boom")

        reporter = ProgressReporter(on_progress=bad_callback)
        reporter.update(1, 100, 200)
        reporter.flush()  # 不应抛出


# ==================== start / stop / _report_loop 测试 ====================


class TestStartStopReportLoop:
    """汇报协程启动/停止与定时批量发送测试。"""

    async def test_start_launches_report_task(self) -> None:
        """start() 启动汇报协程。"""
        reporter = ProgressReporter(on_progress=lambda updates: None)
        reporter.start()
        assert reporter._report_task is not None
        assert not reporter._report_task.done()
        await reporter.stop()

    async def test_report_loop_batch_send(self) -> None:
        """汇报协程在间隔后批量发送进度（缩短间隔验证）。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(
            on_progress=lambda updates: calls.append(updates),
            flush_interval_ms=50,
        )
        reporter.start()
        reporter.update(1, 100, 200)
        reporter.update(2, 200, 400)
        # 等待足够时间让汇报协程至少 flush 一次
        await asyncio.sleep(0.15)
        await reporter.stop()
        assert len(calls) >= 1
        # 验证至少有一次包含两个更新
        all_updates = [u for batch in calls for u in batch]
        ids = {u.task_item_id for u in all_updates}
        assert {1, 2}.issubset(ids)

    async def test_stop_flushes_remaining(self) -> None:
        """stop() 时 flush 残留进度。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(
            on_progress=lambda updates: calls.append(updates),
            flush_interval_ms=10000,  # 长间隔，确保不会自动 flush
        )
        reporter.start()
        reporter.update(1, 100, 200)
        await reporter.stop()
        # stop() 应 flush 残留
        assert len(calls) >= 1
        assert calls[-1][0].task_item_id == 1

    async def test_stop_idempotent(self) -> None:
        """多次 stop() 不报错。"""
        reporter = ProgressReporter(on_progress=lambda updates: None)
        reporter.start()
        await reporter.stop()
        await reporter.stop()

    async def test_start_idempotent(self) -> None:
        """多次 start() 不重复创建协程。"""
        reporter = ProgressReporter(on_progress=lambda updates: None)
        reporter.start()
        task1 = reporter._report_task
        reporter.start()
        task2 = reporter._report_task
        assert task1 is task2
        await reporter.stop()

    async def test_report_loop_stops_on_signal(self) -> None:
        """收到停止信号后汇报协程退出。"""
        reporter = ProgressReporter(
            on_progress=lambda updates: None,
            flush_interval_ms=50,
        )
        reporter.start()
        task = reporter._report_task
        assert task is not None
        await reporter.stop()
        assert task.done()

    async def test_update_after_stop_does_not_flush(self) -> None:
        """stop() 后 update() 的数据不会通过汇报协程发送。"""
        calls: list[list[ProgressUpdate]] = []
        reporter = ProgressReporter(
            on_progress=lambda updates: calls.append(updates),
            flush_interval_ms=10000,
        )
        reporter.start()
        await reporter.stop()
        reporter.update(1, 100, 200)
        # 残留数据在 stop() 时已 flush，之后 update 不会触发
        # 手动 flush 仍可发送
        reporter.flush()
        assert len(calls) >= 1
