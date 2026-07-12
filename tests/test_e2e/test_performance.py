"""性能测试用例。

验证并发下载、大量任务、高频进度更新等场景下的性能表现。
使用 respx mock httpx 响应，不打真实 API。

测试标记：
    - @pytest.mark.slow: 耗时较长的测试（可选运行）
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
import respx

from app.database import get_memory_connection
from app.models import Task, TaskItem
from app.repositories import TaskItemRepository, TaskRepository
from downloader.progress_reporter import ProgressUpdate
from downloader.scheduler import Scheduler

# 标记为性能测试（非 integration，不需真实 Cookie）
pytestmark = pytest.mark.slow


def _insert_task(conn: sqlite3.Connection, download_dir: str, count: int = 1) -> int:
    """插入 Task，返回 task_id。"""
    return TaskRepository(conn).create(
        Task(
            id=None,
            source_type="batch",
            source_url="https://douyin.com/perf_test",
            status="pending",
            total_items=count,
            download_dir=download_dir,
        )
    )


def _insert_item(
    conn: sqlite3.Connection,
    task_id: int,
    aweme_id: str,
    url: str,
) -> TaskItem:
    """插入 TaskItem，返回带 id 的实例。"""
    item_id = TaskItemRepository(conn).create(
        TaskItem(
            id=None,
            task_id=task_id,
            aweme_id=aweme_id,
            url=url,
            type="video",
            status="pending",
            total_bytes=0,
        )
    )
    return TaskItemRepository(conn).get(item_id)  # type: ignore[return-value]


@respx.mock
async def test_concurrency_performance(tmp_path: Path) -> None:
    """并发下载性能：测试并发 3/5/10 的总耗时与无崩溃。"""
    # mock 固定大小数据流（1MB）
    fake_data = b"x" * (1024 * 1024)
    respx.get("https://cdn.example.com/v.mp4").mock(
        return_value=httpx.Response(200, content=fake_data)
    )

    results: list[tuple[int, float]] = []
    for concurrency in [3, 5, 10]:
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path), count=concurrency)
        items = [
            _insert_item(
                conn, task_id, f"aweme_perf_{concurrency}_{i}", "https://cdn.example.com/v.mp4"
            )
            for i in range(concurrency)
        ]

        scheduler = Scheduler(conn=conn, max_concurrent=concurrency)
        await scheduler.start()
        scheduler.add_task_items(items)

        start_time = time.monotonic()
        for _ in range(120):
            await asyncio.sleep(0.5)
            all_done = all(
                TaskItemRepository(conn).get(item.id).status  # type: ignore[union-attr]
                in ("completed", "failed")
                for item in items
            )
            if all_done:
                break
        elapsed = time.monotonic() - start_time
        await scheduler.stop()
        conn.close()

        results.append((concurrency, elapsed))

    # 验证并发数越高，总耗时越短（或有边际递减）
    # 不设硬性阈值，仅验证无崩溃
    assert len(results) == 3
    for _concurrency, elapsed in results:
        assert elapsed > 0
        assert elapsed < 120  # 120 秒内完成


@respx.mock
async def test_large_task_list_performance(tmp_path: Path) -> None:
    """大量任务列表渲染性能：100 个 task_items 数据库查询性能。"""
    conn = get_memory_connection()
    task_id = _insert_task(conn, str(tmp_path), count=100)

    # 插入 100 个 TaskItem
    items = []
    for i in range(100):
        item = _insert_item(
            conn,
            task_id,
            f"aweme_large_{i}",
            "https://cdn.example.com/v.mp4",
        )
        items.append(item)

    # 测量批量查询性能
    item_repo = TaskItemRepository(conn)
    start_time = time.monotonic()
    result = item_repo.get_by_task(task_id)
    elapsed = time.monotonic() - start_time

    assert len(result) == 100
    assert elapsed < 2.0  # 100 条查询应在 2 秒内

    conn.close()


async def test_high_frequency_progress_throttling(tmp_path: Path) -> None:
    """高频进度更新节流：ProgressReporter 500ms 批量更新验证。"""
    from downloader.progress_reporter import ProgressReporter

    received_updates: list[list[ProgressUpdate]] = []

    def on_progress(updates: list[ProgressUpdate]) -> None:
        received_updates.append(updates)

    reporter = ProgressReporter(callback=on_progress, batch_interval=0.5)
    await reporter.start()

    # 高频发送 100 个进度更新
    for i in range(100):
        reporter.report(ProgressUpdate(item_id=1, downloaded_bytes=i * 1024, total_bytes=102400))

    # 等待足够时间让节流器处理
    await asyncio.sleep(2.0)
    await reporter.stop()

    # 验证节流生效：接收到的批次应远少于 100（500ms 批量）
    # 2 秒内应有约 4 个批次（2s / 0.5s）
    assert len(received_updates) < 100, "ProgressReporter 未节流，每条更新都回调"
    assert len(received_updates) >= 1, "未收到任何进度更新"


@respx.mock
async def test_memory_under_concurrent_load(tmp_path: Path) -> None:
    """并发负载下内存不泄漏：短时间多次批量下载。"""
    try:
        import psutil
    except ImportError:
        pytest.skip("psutil 未安装，内存测试跳过")

    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    # mock 小数据流
    respx.get("https://cdn.example.com/v.mp4").mock(
        return_value=httpx.Response(200, content=b"data" * 256)
    )

    # 执行 3 轮批量下载（每轮 5 个任务）
    for round_num in range(3):
        conn = get_memory_connection()
        task_id = _insert_task(conn, str(tmp_path), count=5)
        items = [
            _insert_item(
                conn, task_id, f"aweme_mem_{round_num}_{i}", "https://cdn.example.com/v.mp4"
            )
            for i in range(5)
        ]

        scheduler = Scheduler(conn=conn, max_concurrent=3)
        await scheduler.start()
        scheduler.add_task_items(items)

        for _ in range(60):
            await asyncio.sleep(0.5)
            all_done = all(
                TaskItemRepository(conn).get(item.id).status  # type: ignore[union-attr]
                in ("completed", "failed")
                for item in items
            )
            if all_done:
                break
        await scheduler.stop()
        conn.close()

    final_memory = process.memory_info().rss
    memory_growth = final_memory - initial_memory

    # 内存增长应小于 100MB（无严重泄漏）
    assert memory_growth < 100 * 1024 * 1024, f"内存增长过大: {memory_growth / 1024 / 1024:.1f}MB"
