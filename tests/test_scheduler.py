"""Scheduler 单元测试。

覆盖并发控制、队列管理、暂停/恢复、去重、回调、启动恢复等场景。
使用 respx mock httpx 响应，不打真实网络请求。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import httpx
import respx

from app.database import get_memory_connection
from app.models import Task, TaskItem
from app.repositories import TaskItemRepository, TaskRepository
from downloader.progress_reporter import ProgressUpdate
from downloader.scheduler import (
    DEFAULT_MAX_CONCURRENT,
    MAX_CONCURRENT_LIMIT,
    Scheduler,
)

# ==================== 常量测试 ====================


class TestConstants:
    """模块级常量契约测试。"""

    def test_default_max_concurrent_3(self) -> None:
        assert DEFAULT_MAX_CONCURRENT == 3

    def test_max_concurrent_limit_10(self) -> None:
        assert MAX_CONCURRENT_LIMIT == 10


# ==================== 并发控制测试 ====================


class TestConcurrencyControl:
    """并发数 clamp 与动态调整测试。"""

    def test_default_concurrency_3(self) -> None:
        """默认并发数为 3。"""
        scheduler = _make_scheduler()
        assert scheduler._max_concurrent == 3

    def test_max_concurrency_clamped_to_10(self) -> None:
        """并发数超过 10 被 clamp 到 10。"""
        scheduler = _make_scheduler(max_concurrent=15)
        assert scheduler._max_concurrent == 10

    def test_min_concurrency_clamped_to_1(self) -> None:
        """并发数低于 1 被 clamp 到 1。"""
        scheduler = _make_scheduler(max_concurrent=0)
        assert scheduler._max_concurrent == 1

    def test_set_max_concurrent_dynamic(self) -> None:
        """动态调整并发数。"""
        scheduler = _make_scheduler(max_concurrent=3)
        scheduler.set_max_concurrent(5)
        assert scheduler._max_concurrent == 5

    def test_set_max_concurrent_clamped(self) -> None:
        """动态调整并发数也 clamp。"""
        scheduler = _make_scheduler(max_concurrent=3)
        scheduler.set_max_concurrent(20)
        assert scheduler._max_concurrent == 10

    def test_set_max_concurrent_no_change(self) -> None:
        """设置相同值时不变。"""
        scheduler = _make_scheduler(max_concurrent=3)
        old_semaphore = scheduler._semaphore
        scheduler.set_max_concurrent(3)
        assert scheduler._semaphore is old_semaphore

    @respx.mock
    async def test_semaphore_limits_concurrency(self, tmp_path: Path) -> None:
        """并发数不超过 max_concurrent。"""
        concurrent = 0
        max_seen = 0

        async def tracking_handler(request: httpx.Request) -> httpx.Response:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.3)
            concurrent -= 1
            return httpx.Response(200, content=b"data")

        respx.get("https://cdn.example.com/v.mp4").mock(side_effect=tracking_handler)

        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        items = [
            _insert_item(conn, task_id, f"aweme{i}", "https://cdn.example.com/v.mp4")
            for i in range(5)
        ]

        scheduler = _make_scheduler(conn=conn, max_concurrent=2)
        await scheduler.start()
        scheduler.add_task_items(items)
        await asyncio.sleep(2)
        await scheduler.stop()

        assert max_seen <= 2


# ==================== 队列管理与去重测试 ====================


class TestQueueManagement:
    """队列管理与去重逻辑测试。"""

    def test_add_task_items_enqueues(self) -> None:
        """add_task_items 将项加入队列。"""
        scheduler = _make_scheduler()
        item = _make_item(aweme_id="aweme001")
        scheduler.add_task_items([item])
        assert scheduler._queue.qsize() == 1

    def test_add_multiple_items(self) -> None:
        """添加多项全部入队。"""
        scheduler = _make_scheduler()
        items = [_make_item(aweme_id=f"aweme{i}") for i in range(3)]
        scheduler.add_task_items(items)
        assert scheduler._queue.qsize() == 3

    def test_dedup_completed_aweme_id_skipped(self) -> None:
        """已完成 aweme_id 不入队。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="completed")

        scheduler = _make_scheduler(conn=conn)
        new_item = _make_item(aweme_id="aweme001")
        scheduler.add_task_items([new_item])
        assert scheduler._queue.qsize() == 0

    def test_dedup_none_aweme_id_not_skipped(self) -> None:
        """aweme_id 为 None 时不跳过。"""
        scheduler = _make_scheduler()
        item = _make_item(aweme_id=None)
        scheduler.add_task_items([item])
        assert scheduler._queue.qsize() == 1

    def test_dedup_non_completed_not_skipped(self) -> None:
        """aweme_id 存在但状态非 completed 时不跳过。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="failed")

        scheduler = _make_scheduler(conn=conn)
        new_item = _make_item(aweme_id="aweme001")
        scheduler.add_task_items([new_item])
        assert scheduler._queue.qsize() == 1


# ==================== 启动/停止测试 ====================


class TestStartStop:
    """启动/停止生命周期测试。"""

    async def test_start_launches_loop(self) -> None:
        """start() 启动调度循环。"""
        scheduler = _make_scheduler()
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._loop_task is not None
        await scheduler.stop()

    async def test_start_idempotent(self) -> None:
        """重复 start() 不创建多个循环。"""
        scheduler = _make_scheduler()
        await scheduler.start()
        loop_task = scheduler._loop_task
        await scheduler.start()
        assert scheduler._loop_task is loop_task
        await scheduler.stop()

    async def test_stop_sets_running_false(self) -> None:
        """stop() 设置 _running=False。"""
        scheduler = _make_scheduler()
        await scheduler.start()
        await scheduler.stop()
        assert scheduler._running is False

    async def test_stop_idempotent(self) -> None:
        """重复 stop() 不报错。"""
        scheduler = _make_scheduler()
        await scheduler.start()
        await scheduler.stop()
        await scheduler.stop()

    async def test_stop_cancels_running_tasks(self) -> None:
        """stop() 取消进行中的下载任务。"""

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, content=b"data")

        with respx.mock:
            respx.get("https://cdn.example.com/v.mp4").mock(side_effect=slow_handler)
            conn = get_memory_connection()
            task_id = _insert_task(conn, "/tmp/test")
            item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

            scheduler = _make_scheduler(conn=conn)
            await scheduler.start()
            scheduler.add_task_items([item])
            await asyncio.sleep(0.5)
            assert len(scheduler._tasks) > 0
            await scheduler.stop()
            assert len(scheduler._tasks) == 0


# ==================== 回调测试 ====================


class TestCallbacks:
    """下载完成/失败回调测试。"""

    @respx.mock
    async def test_on_item_completed_callback(self, tmp_path: Path) -> None:
        """下载成功触发 on_item_completed 回调。"""
        respx.get("https://cdn.example.com/v.mp4").mock(
            return_value=httpx.Response(200, content=b"video_data")
        )
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        completed_ids: list[int] = []
        scheduler = _make_scheduler(
            conn=conn, on_item_completed=lambda tid: completed_ids.append(tid)
        )
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(1)
        await scheduler.stop()

        assert item.id in completed_ids

    @respx.mock
    async def test_on_item_failed_callback(self, tmp_path: Path) -> None:
        """下载失败触发 on_item_failed 回调。"""
        respx.get("https://cdn.example.com/v.mp4").mock(return_value=httpx.Response(404))
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        failed_ids: list[tuple[int, str]] = []
        scheduler = _make_scheduler(
            conn=conn, on_item_failed=lambda tid, reason: failed_ids.append((tid, reason))
        )
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(1)
        await scheduler.stop()

        assert len(failed_ids) == 1
        assert failed_ids[0][0] == item.id

    @respx.mock
    async def test_on_progress_callback(self, tmp_path: Path) -> None:
        """下载过程触发 on_progress 回调。"""
        data = b"x" * (64 * 1024 + 100)
        respx.get("https://cdn.example.com/v.mp4").mock(
            return_value=httpx.Response(200, content=data)
        )
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        progress_updates: list[list[ProgressUpdate]] = []
        scheduler = _make_scheduler(
            conn=conn, on_progress=lambda updates: progress_updates.append(updates)
        )
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(1)
        await scheduler.stop()

        # ProgressReporter 节流 500ms，至少应该有一些更新
        assert len(progress_updates) > 0


# ==================== 暂停/恢复测试 ====================


class TestPauseResume:
    """暂停/恢复测试。"""

    @respx.mock
    async def test_pause_sets_status_paused(self, tmp_path: Path) -> None:
        """pause() 将 status 置为 paused。"""

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, content=b"data")

        respx.get("https://cdn.example.com/v.mp4").mock(side_effect=slow_handler)
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(0.5)  # 等待下载开始
        await scheduler.pause(item.id)

        assert _get_item_status(conn, item.id) == "paused"
        await scheduler.stop()

    @respx.mock
    async def test_pause_removes_from_tasks(self, tmp_path: Path) -> None:
        """pause() 后从 _tasks 字典移除。"""

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, content=b"data")

        respx.get("https://cdn.example.com/v.mp4").mock(side_effect=slow_handler)
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(0.5)
        await scheduler.pause(item.id)

        assert item.id not in scheduler._tasks
        await scheduler.stop()

    @respx.mock
    async def test_resume_recreates_task(self, tmp_path: Path) -> None:
        """resume() 重新创建 asyncio.Task。"""

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, content=b"data")

        respx.get("https://cdn.example.com/v.mp4").mock(side_effect=slow_handler)
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(0.5)
        await scheduler.pause(item.id)
        assert item.id not in scheduler._tasks

        await scheduler.resume(item.id)
        assert item.id in scheduler._tasks
        await scheduler.stop()

    @respx.mock
    async def test_resume_non_paused_skipped(self, tmp_path: Path) -> None:
        """resume() 对非 paused 状态的项不操作。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(
            conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="completed"
        )

        scheduler = _make_scheduler(conn=conn)
        await scheduler.start()
        await scheduler.resume(item.id)
        assert item.id not in scheduler._tasks
        await scheduler.stop()

    @respx.mock
    async def test_resume_nonexistent_skipped(self) -> None:
        """resume() 对不存在的 id 不报错。"""
        scheduler = _make_scheduler()
        await scheduler.start()
        await scheduler.resume(99999)  # 不应报错
        await scheduler.stop()

    @respx.mock
    async def test_pause_all(self, tmp_path: Path) -> None:
        """pause_all() 暂停所有进行中任务。"""

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, content=b"data")

        respx.get("https://cdn.example.com/v.mp4").mock(side_effect=slow_handler)
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        items = [
            _insert_item(conn, task_id, f"aweme{i}", "https://cdn.example.com/v.mp4")
            for i in range(3)
        ]

        scheduler = _make_scheduler(conn=conn, max_concurrent=3)
        await scheduler.start()
        scheduler.add_task_items(items)
        await asyncio.sleep(0.5)
        await scheduler.pause_all()

        assert len(scheduler._tasks) == 0
        for item in items:
            assert _get_item_status(conn, item.id) == "paused"
        await scheduler.stop()

    @respx.mock
    async def test_resume_all(self, tmp_path: Path) -> None:
        """resume_all() 恢复所有 paused 任务。"""

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, content=b"data")

        respx.get("https://cdn.example.com/v.mp4").mock(side_effect=slow_handler)
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        items = [
            _insert_item(conn, task_id, f"aweme{i}", "https://cdn.example.com/v.mp4")
            for i in range(3)
        ]

        scheduler = _make_scheduler(conn=conn, max_concurrent=3)
        await scheduler.start()
        scheduler.add_task_items(items)
        await asyncio.sleep(0.5)
        await scheduler.pause_all()
        assert len(scheduler._tasks) == 0

        await scheduler.resume_all()
        assert len(scheduler._tasks) == 3
        await scheduler.stop()


# ==================== 启动恢复测试 ====================


class TestRestore:
    """启动恢复（restore_pending_tasks）测试。"""

    async def test_restore_resets_downloading_to_paused(self) -> None:
        """启动恢复时 downloading → paused 重置。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        item = _insert_item(
            conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="downloading"
        )

        scheduler = _make_scheduler(conn=conn)
        await scheduler.restore_pending_tasks()

        assert _get_item_status(conn, item.id) == "paused"
        await scheduler.stop()

    async def test_restore_enqueues_pending(self) -> None:
        """启动恢复时 pending 项加入队列。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="pending")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.restore_pending_tasks()
        assert scheduler._queue.qsize() == 1
        await scheduler.stop()

    async def test_restore_enqueues_paused(self) -> None:
        """启动恢复时 paused 项加入队列。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="paused")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.restore_pending_tasks()
        assert scheduler._queue.qsize() == 1
        await scheduler.stop()

    async def test_restore_skips_completed(self) -> None:
        """启动恢复时跳过 completed 项。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="completed")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.restore_pending_tasks()
        assert scheduler._queue.qsize() == 0
        await scheduler.stop()

    async def test_restore_skips_failed(self) -> None:
        """启动恢复时跳过 failed 项。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="failed")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.restore_pending_tasks()
        assert scheduler._queue.qsize() == 0
        await scheduler.stop()

    async def test_restore_mixed_statuses(self) -> None:
        """混合状态：只入队 pending + paused（downloading 先重置为 paused）。"""
        conn = get_memory_connection()
        task_id = _insert_task(conn, "/tmp/test")
        _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4", status="completed")
        _insert_item(conn, task_id, "aweme002", "https://cdn.example.com/v.mp4", status="failed")
        _insert_item(conn, task_id, "aweme003", "https://cdn.example.com/v.mp4", status="pending")
        item4 = _insert_item(
            conn, task_id, "aweme004", "https://cdn.example.com/v.mp4", status="downloading"
        )
        _insert_item(conn, task_id, "aweme005", "https://cdn.example.com/v.mp4", status="paused")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.restore_pending_tasks()
        # pending(1) + downloading→paused(1) + paused(1) = 3
        assert scheduler._queue.qsize() == 3
        assert _get_item_status(conn, item4.id) == "paused"
        await scheduler.stop()


# ==================== 调度循环测试 ====================


class TestScheduleLoop:
    """调度循环处理队列测试。"""

    @respx.mock
    async def test_scheduler_processes_queue(self, tmp_path: Path) -> None:
        """调度循环从队列取任务执行。"""
        respx.get("https://cdn.example.com/v.mp4").mock(
            return_value=httpx.Response(200, content=b"video_data")
        )
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        item = _insert_item(conn, task_id, "aweme001", "https://cdn.example.com/v.mp4")

        scheduler = _make_scheduler(conn=conn)
        await scheduler.start()
        scheduler.add_task_items([item])
        await asyncio.sleep(1)
        await scheduler.stop()

        assert _get_item_status(conn, item.id) == "completed"

    @respx.mock
    async def test_scheduler_multiple_items(self, tmp_path: Path) -> None:
        """多个任务项依次处理。"""
        respx.get("https://cdn.example.com/v.mp4").mock(
            return_value=httpx.Response(200, content=b"video_data")
        )
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path))
        items = [
            _insert_item(conn, task_id, f"aweme{i}", "https://cdn.example.com/v.mp4")
            for i in range(3)
        ]

        scheduler = _make_scheduler(conn=conn)
        await scheduler.start()
        scheduler.add_task_items(items)
        await asyncio.sleep(2)
        await scheduler.stop()

        for item in items:
            assert _get_item_status(conn, item.id) == "completed"


# ==================== 辅助函数 ====================


def _make_scheduler(
    conn: sqlite3.Connection | None = None,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    on_item_completed: object | None = None,
    on_item_failed: object | None = None,
    on_progress: object | None = None,
) -> Scheduler:
    """创建测试用 Scheduler。"""
    if conn is None:
        conn = get_memory_connection()
    return Scheduler(
        conn=conn,
        max_concurrent=max_concurrent,
        on_item_completed=on_item_completed,  # type: ignore[arg-type]
        on_item_failed=on_item_failed,  # type: ignore[arg-type]
        on_progress=on_progress,  # type: ignore[arg-type]
    )


def _insert_task(conn: sqlite3.Connection, download_dir: str = "/tmp/test") -> int:
    """插入一条 Task，返回 task_id。"""
    return TaskRepository(conn).create(
        Task(
            id=None,
            source_type="single",
            source_url="https://douyin.com/video/123",
            status="pending",
            total_items=1,
            download_dir=download_dir,
        )
    )


def _insert_item(
    conn: sqlite3.Connection,
    task_id: int,
    aweme_id: str,
    url: str,
    item_type: str = "video",
    status: str = "pending",
) -> TaskItem:
    """插入一条 TaskItem，返回带正确 id 的 TaskItem。"""
    item_id = TaskItemRepository(conn).create(
        TaskItem(
            id=None,
            task_id=task_id,
            aweme_id=aweme_id,
            url=url,
            type=item_type,
            status=status,
        )
    )
    item = TaskItemRepository(conn).get(item_id)
    assert item is not None
    return item


def _make_item(
    aweme_id: str | None = "aweme001",
    url: str = "https://cdn.example.com/v.mp4",
    item_type: str = "video",
    status: str = "pending",
    item_id: int = 1,
    task_id: int = 1,
) -> TaskItem:
    """创建未持久化的 TaskItem（用于 add_task_items 入队测试）。"""
    return TaskItem(
        id=item_id,
        task_id=task_id,
        aweme_id=aweme_id,
        url=url,
        type=item_type,
        status=status,
    )


def _get_item_status(conn: sqlite3.Connection, item_id: int) -> str:
    row = conn.execute("SELECT status FROM task_items WHERE id=?", (item_id,)).fetchone()
    return row["status"] if row else ""
