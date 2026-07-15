"""DownloadBridge 真实下载与暂停恢复端到端测试。

验证 DownloadBridge 通过 AsyncWorker 驱动 Scheduler 完成真实下载，
以及暂停/恢复的完整链路：
    UI 控制信号 → DownloadBridge 槽 → AsyncWorker → Scheduler → 真实下载 → 文件落盘

需要真实 Cookie（.test_cookie.txt）与真实 aweme_id（.test_aweme_id.txt）。
DownloadBridge 和 AsyncWorker 是 QObject/QThread，需要 QApplication（pytest-qt qapp）。
无 Cookie 时通过 fixture 自动 skip。
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from pathlib import Path

import pytest

from app.models import Cookie, Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler
from worker.async_worker import AsyncWorker
from worker.download_bridge import DownloadBridge
from worker.signals import ControlSignals, WorkerSignals

pytestmark = pytest.mark.integration


async def test_download_bridge_download_e2e(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """DownloadBridge 真实下载：解析直链 → 桥接启动 → 完成 → 文件落盘。"""
    # 1. 注入 Cookie 与组装真实组件
    cookie_repo = CookieRepository(clean_db)
    cookie_repo.add(Cookie(id=None, content=real_cookie, status="valid"))
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    # 2. 解析视频获取直链
    share_url = f"https://www.douyin.com/video/{real_aweme_id}"
    parsed = await url_parser.parse(share_url)
    assert parsed.type == "video"
    assert parsed.aweme_id == real_aweme_id

    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    assert video_info.no_watermark_url is not None
    assert video_info.no_watermark_url.startswith("http")

    # 3. 创建 Task 与 TaskItem
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="single",
            source_url=share_url,
            status="pending",
            total_items=1,
            download_dir=str(tmp_download_dir),
        )
    )
    item_id = item_repo.create(
        TaskItem(
            id=None,
            task_id=task_id,
            aweme_id=real_aweme_id,
            url=video_info.no_watermark_url,
            title=video_info.title,
            author=video_info.author,
            type="video",
            cover_url=video_info.cover_url,
            status="pending",
            total_bytes=0,
        )
    )

    # 4. 创建 Scheduler、AsyncWorker、DownloadBridge
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    async_worker = AsyncWorker()
    async_worker.start()

    try:
        worker_signals = WorkerSignals()
        control_signals = ControlSignals()
        bridge = DownloadBridge(
            async_worker=async_worker,
            scheduler=scheduler,
            task_item_repository=item_repo,
            task_repository=task_repo,
            worker_signals=worker_signals,
            control_signals=control_signals,
        )

        # 5. 初始化 Scheduler（设置并发数 + 启动调度循环）
        bridge.init_scheduler(1)
        await asyncio.sleep(0.5)
        qapp.processEvents()

        # 6. 监听 item_completed 信号
        received_completed: list[int] = []
        worker_signals.item_completed.connect(lambda tid: received_completed.append(tid))

        # 7. 通过控制信号启动下载
        bridge._control_signals.start_download.emit([item_id])
        await asyncio.sleep(0.3)
        qapp.processEvents()

        # 8. 等待下载完成（最长 60 秒）
        item = None
        for _ in range(120):
            qapp.processEvents()
            await asyncio.sleep(0.5)
            item = item_repo.get(item_id)
            assert item is not None
            if item.status in ("completed", "failed"):
                break

        qapp.processEvents()

        # 9. 验证结果
        assert item is not None
        assert item.status == "completed", f"下载失败: {item.fail_reason}"
        assert received_completed == [item_id]
        assert item.local_path is not None
        downloaded_file = Path(item.local_path)
        assert downloaded_file.exists()
        assert downloaded_file.stat().st_size > 0

        # 10. 清理下载文件
        if downloaded_file.exists():
            downloaded_file.unlink()
    finally:
        # 停止 Scheduler 与 AsyncWorker
        if async_worker.isRunning():
            with contextlib.suppress(Exception):
                async_worker.submit(scheduler.stop()).result(timeout=10)
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 async_worker.stop() 之前通过 submit() 在 worker 线程内关闭
        with contextlib.suppress(Exception):
            async_worker.submit(http_client.close()).result(timeout=10)
        async_worker.stop()


async def test_download_bridge_pause_resume_e2e(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """DownloadBridge 暂停/恢复：启动 → 暂停 → 验证状态 → 恢复 → 完成。"""
    # 1. 注入 Cookie 与组装真实组件
    cookie_repo = CookieRepository(clean_db)
    cookie_repo.add(Cookie(id=None, content=real_cookie, status="valid"))
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    # 2. 解析视频获取直链
    share_url = f"https://www.douyin.com/video/{real_aweme_id}"
    parsed = await url_parser.parse(share_url)
    assert parsed.type == "video"
    assert parsed.aweme_id == real_aweme_id

    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    assert video_info.no_watermark_url is not None
    assert video_info.no_watermark_url.startswith("http")

    # 3. 创建 Task 与 TaskItem
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="single",
            source_url=share_url,
            status="pending",
            total_items=1,
            download_dir=str(tmp_download_dir),
        )
    )
    item_id = item_repo.create(
        TaskItem(
            id=None,
            task_id=task_id,
            aweme_id=real_aweme_id,
            url=video_info.no_watermark_url,
            title=video_info.title,
            author=video_info.author,
            type="video",
            cover_url=video_info.cover_url,
            status="pending",
            total_bytes=0,
        )
    )

    # 4. 创建 Scheduler、AsyncWorker、DownloadBridge
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    async_worker = AsyncWorker()
    async_worker.start()

    try:
        worker_signals = WorkerSignals()
        control_signals = ControlSignals()
        bridge = DownloadBridge(
            async_worker=async_worker,
            scheduler=scheduler,
            task_item_repository=item_repo,
            task_repository=task_repo,
            worker_signals=worker_signals,
            control_signals=control_signals,
        )

        # 5. 初始化 Scheduler 并启动下载
        bridge.init_scheduler(1)
        await asyncio.sleep(0.5)
        qapp.processEvents()

        received_completed: list[int] = []
        worker_signals.item_completed.connect(lambda tid: received_completed.append(tid))

        bridge._control_signals.start_download.emit([item_id])
        await asyncio.sleep(0.3)
        qapp.processEvents()

        # 6. 等待下载开始
        item = None
        for _ in range(20):
            qapp.processEvents()
            await asyncio.sleep(0.5)
            item = item_repo.get(item_id)
            assert item is not None
            if item.status == "downloading" and item.downloaded_bytes > 0:
                break

        # 7. 暂停下载
        bridge._control_signals.pause_download.emit(item_id)
        await asyncio.sleep(1.0)
        qapp.processEvents()

        item = item_repo.get(item_id)
        assert item is not None
        assert item.status == "paused"

        # 8. 恢复下载
        bridge._control_signals.resume_download.emit(item_id)
        await asyncio.sleep(0.3)
        qapp.processEvents()

        # 9. 等待下载完成（最长 60 秒）
        for _ in range(120):
            qapp.processEvents()
            await asyncio.sleep(0.5)
            item = item_repo.get(item_id)
            assert item is not None
            if item.status in ("completed", "failed"):
                break

        qapp.processEvents()

        # 10. 验证结果
        assert item is not None
        assert item.status == "completed", f"恢复后下载失败: {item.fail_reason}"
        assert received_completed == [item_id]
        assert item.local_path is not None
        downloaded_file = Path(item.local_path)
        assert downloaded_file.exists()
        assert downloaded_file.stat().st_size > 0

        # 11. 清理下载文件
        if downloaded_file.exists():
            downloaded_file.unlink()
    finally:
        # 停止 Scheduler 与 AsyncWorker
        if async_worker.isRunning():
            with contextlib.suppress(Exception):
                async_worker.submit(scheduler.stop()).result(timeout=10)
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 async_worker.stop() 之前通过 submit() 在 worker 线程内关闭
        with contextlib.suppress(Exception):
            async_worker.submit(http_client.close()).result(timeout=10)
        async_worker.stop()
