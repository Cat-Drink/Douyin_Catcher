"""DownloadBridge 单元测试。

覆盖控制信号 → Scheduler 方法转发、回调 → UI 信号转发、
task_completed 检测、断点续传恢复等场景。
使用 mock Scheduler + mock repositories + 真实 WorkerSignals/ControlSignals。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.models import TaskItem
from downloader.progress_reporter import ProgressUpdate
from worker.download_bridge import DownloadBridge
from worker.signals import ControlSignals, WorkerSignals

# ==================== 辅助函数 ====================


def _make_task_item(
    item_id: int = 1,
    task_id: int = 1,
    aweme_id: str = "aweme_001",
    status: str = "pending",
) -> TaskItem:
    """构造 TaskItem 实例。"""
    return TaskItem(
        id=item_id,
        task_id=task_id,
        aweme_id=aweme_id,
        url="https://example.com/v.mp4",
        status=status,
    )


def _make_mock_scheduler() -> MagicMock:
    """构造 mock Scheduler。"""
    scheduler = MagicMock()
    scheduler.start = AsyncMock()
    scheduler.stop = AsyncMock()
    scheduler.pause = AsyncMock()
    scheduler.resume = AsyncMock()
    scheduler.pause_all = AsyncMock()
    scheduler.resume_all = AsyncMock()
    scheduler.restore_pending_tasks = AsyncMock()
    scheduler.add_task_items = MagicMock()
    scheduler.set_max_concurrent = MagicMock()
    # ProgressReporter mock
    scheduler._progress_reporter = MagicMock()
    return scheduler


def _make_bridge(
    qapp,
    async_worker,
    scheduler=None,
    task_item_repo=None,
    task_repo=None,
) -> DownloadBridge:
    """构造 DownloadBridge 实例。"""
    scheduler = scheduler or _make_mock_scheduler()
    task_item_repo = task_item_repo or MagicMock()
    task_repo = task_repo or MagicMock()
    worker_signals = WorkerSignals()
    control_signals = ControlSignals()
    return DownloadBridge(
        async_worker=async_worker,
        scheduler=scheduler,
        task_item_repository=task_item_repo,
        task_repository=task_repo,
        worker_signals=worker_signals,
        control_signals=control_signals,
    )


# ==================== 控制信号 → Scheduler 方法测试 ====================


class TestControlSignalForwarding:
    """控制信号 → Scheduler 方法转发测试。"""

    def test_start_download_calls_add_task_items(self, qapp, async_worker) -> None:
        """emit start_download → scheduler.add_task_items 被调用。"""
        scheduler = _make_mock_scheduler()
        item_repo = MagicMock()
        item_repo.get = MagicMock(return_value=_make_task_item(1))
        bridge = _make_bridge(qapp, async_worker, scheduler, item_repo)

        bridge._control_signals.start_download.emit([1])
        # 等待异步执行
        import time

        time.sleep(0.3)

        scheduler.add_task_items.assert_called_once()
        called_items = scheduler.add_task_items.call_args[0][0]
        assert len(called_items) == 1

    def test_pause_download_calls_scheduler_pause(self, qapp, async_worker) -> None:
        """emit pause_download → scheduler.pause 被调用。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge._control_signals.pause_download.emit(42)
        import time

        time.sleep(0.2)

        scheduler.pause.assert_called_once_with(42)

    def test_resume_download_calls_scheduler_resume(self, qapp, async_worker) -> None:
        """emit resume_download → scheduler.resume 被调用。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge._control_signals.resume_download.emit(42)
        import time

        time.sleep(0.2)

        scheduler.resume.assert_called_once_with(42)

    def test_pause_all_calls_scheduler_pause_all(self, qapp, async_worker) -> None:
        """emit pause_all → scheduler.pause_all 被调用。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge._control_signals.pause_all.emit()
        import time

        time.sleep(0.2)

        scheduler.pause_all.assert_called_once()

    def test_resume_all_calls_scheduler_resume_all(self, qapp, async_worker) -> None:
        """emit resume_all → scheduler.resume_all 被调用。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge._control_signals.resume_all.emit()
        import time

        time.sleep(0.2)

        scheduler.resume_all.assert_called_once()

    def test_init_scheduler_sets_concurrency(self, qapp, async_worker) -> None:
        """init_scheduler(5) → set_max_concurrent(5) + start() 被提交。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge.init_scheduler(5)
        import time

        time.sleep(0.2)

        scheduler.set_max_concurrent.assert_called_once_with(5)
        scheduler.start.assert_awaited_once()


# ==================== 回调 → UI 信号测试 ====================


class TestCallbackToSignal:
    """Scheduler/ProgressReporter 回调 → UI 信号转发测试。"""

    def test_on_item_completed_emits_signal(self, qapp, async_worker) -> None:
        """on_item_completed(1) → item_completed emit (1)。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[int] = []
        bridge._worker_signals.item_completed.connect(lambda tid: received.append(tid))

        bridge.on_item_completed(1)
        qapp.processEvents()

        assert received == [1]

    def test_on_item_failed_emits_signal(self, qapp, async_worker) -> None:
        """on_item_failed(1, "网络错误") → item_failed emit (1, "网络错误")。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[tuple[int, str]] = []
        bridge._worker_signals.item_failed.connect(
            lambda tid, reason: received.append((tid, reason))
        )

        bridge.on_item_failed(1, "网络错误")
        qapp.processEvents()

        assert received == [(1, "网络错误")]

    def test_on_progress_emits_signal(self, qapp, async_worker) -> None:
        """on_progress([update1, update2]) → progress_updated emit 同列表。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[list] = []
        bridge._worker_signals.progress_updated.connect(lambda updates: received.append(updates))

        updates = [
            ProgressUpdate(task_item_id=1, downloaded_bytes=100, total_bytes=1000),
            ProgressUpdate(task_item_id=2, downloaded_bytes=200, total_bytes=2000),
        ]
        bridge.on_progress(updates)
        qapp.processEvents()

        assert len(received) == 1
        assert received[0] == updates

    def test_on_all_cookies_invalid_emits_signal(self, qapp, async_worker) -> None:
        """on_all_cookies_invalid() → cookie_invalid emit。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[str] = []
        bridge._worker_signals.cookie_invalid.connect(lambda msg: received.append(msg))

        bridge.on_all_cookies_invalid()
        qapp.processEvents()

        assert len(received) == 1
        assert "Cookie" in received[0]


# ==================== task_completed 检测测试 ====================


class TestTaskCompletedDetection:
    """task_completed 信号检测测试。"""

    def test_task_completed_emitted_when_all_items_done(self, qapp, async_worker) -> None:
        """某 task 下所有 task_items completed → task_completed emit (task_id)。"""
        bridge = _make_bridge(qapp, async_worker)

        # 构造：task_id=1 下有 3 个子项，全部 completed
        items = [
            _make_task_item(1, task_id=1, status="completed"),
            _make_task_item(2, task_id=1, status="completed"),
            _make_task_item(3, task_id=1, status="completed"),
        ]
        bridge._task_item_repo.get = MagicMock(return_value=items[2])
        bridge._task_item_repo.get_by_task = MagicMock(return_value=items)

        received: list[int] = []
        bridge._worker_signals.task_completed.connect(lambda tid: received.append(tid))

        bridge.on_item_completed(3)
        qapp.processEvents()

        assert received == [1]

    def test_task_completed_not_emitted_when_items_pending(self, qapp, async_worker) -> None:
        """某 task 下有未完成子项 → 不 emit task_completed。"""
        bridge = _make_bridge(qapp, async_worker)

        items = [
            _make_task_item(1, task_id=1, status="completed"),
            _make_task_item(2, task_id=1, status="downloading"),
            _make_task_item(3, task_id=1, status="completed"),
        ]
        bridge._task_item_repo.get = MagicMock(return_value=items[2])
        bridge._task_item_repo.get_by_task = MagicMock(return_value=items)

        received: list[int] = []
        bridge._worker_signals.task_completed.connect(lambda tid: received.append(tid))

        bridge.on_item_completed(3)
        qapp.processEvents()

        assert received == []

    def test_task_completed_not_emitted_when_item_not_found(self, qapp, async_worker) -> None:
        """task_item 不存在 → 不 emit task_completed。"""
        bridge = _make_bridge(qapp, async_worker)
        bridge._task_item_repo.get = MagicMock(return_value=None)

        received: list[int] = []
        bridge._worker_signals.task_completed.connect(lambda tid: received.append(tid))

        bridge.on_item_completed(999)
        qapp.processEvents()

        assert received == []


# ==================== 断点续传恢复测试 ====================


class TestRestorePendingTasks:
    """断点续传恢复测试。"""

    def test_restore_pending_tasks_calls_scheduler(self, qapp, async_worker) -> None:
        """restore_pending_tasks() → scheduler.restore_pending_tasks() 被提交。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge.restore_pending_tasks()
        import time

        time.sleep(0.2)

        scheduler.restore_pending_tasks.assert_awaited_once()

    def test_restore_on_app_startup(self, qapp, async_worker) -> None:
        """模拟应用启动：init_scheduler + restore_pending_tasks 顺序调用。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        bridge.init_scheduler(3)
        bridge.restore_pending_tasks()
        import time

        time.sleep(0.3)

        scheduler.set_max_concurrent.assert_called_once_with(3)
        scheduler.start.assert_awaited_once()
        scheduler.restore_pending_tasks.assert_awaited_once()


# ==================== 信号连接测试 ====================


class TestSignalConnection:
    """信号连接完整性测试。"""

    def test_scheduler_callbacks_set(self, qapp, async_worker) -> None:
        """DownloadBridge 初始化后引用正确的 Scheduler。"""
        scheduler = _make_mock_scheduler()
        bridge = _make_bridge(qapp, async_worker, scheduler)

        assert bridge._scheduler is scheduler
        assert bridge._worker_signals is not None
        assert bridge._control_signals is not None

    def test_start_download_skips_nonexistent_items(self, qapp, async_worker) -> None:
        """start_download 中不存在的 task_item_id 被跳过。"""
        scheduler = _make_mock_scheduler()
        item_repo = MagicMock()
        item_repo.get = MagicMock(return_value=None)
        bridge = _make_bridge(qapp, async_worker, scheduler, item_repo)

        bridge._control_signals.start_download.emit([999])
        import time

        time.sleep(0.2)

        # add_task_items 不应被调用（所有项都不存在）
        scheduler.add_task_items.assert_not_called()
