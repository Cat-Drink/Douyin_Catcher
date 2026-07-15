"""UI DownloadPage 下载流程端到端测试。

验证 DownloadPage 通过 DownloadBridge 驱动真实下载的完整链路：
    解析直链 → 创建 Task/TaskItem → DownloadPage.refresh() 加载列表 →
    控制信号启动下载 → Bridge → AsyncWorker → Scheduler → 真实下载 →
    WorkerSignals.item_completed → DownloadPage 更新行状态与状态栏 → 文件落盘

需要真实 Cookie（.test_cookie.txt）与真实 aweme_id（.test_aweme_id.txt）。
DownloadPage / DownloadBridge / AsyncWorker 均为 QWidget / QObject / QThread，
需要 QApplication（pytest-qt qapp）。无 Cookie 时通过 fixture 自动 skip。
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
from ui.pages.download_page import DownloadPage
from worker.async_worker import AsyncWorker
from worker.download_bridge import DownloadBridge
from worker.signals import ControlSignals, WorkerSignals

pytestmark = pytest.mark.integration


async def test_ui_download_page_flow_e2e(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """DownloadPage 端到端下载流程：refresh 加载 → 启动下载 → UI 显示完成 → 文件落盘。"""
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

        # 5. 创建 DownloadPage（构造时自动连接 bridge 的 WorkerSignals）
        page = DownloadPage(download_bridge=bridge, conn=clean_db)

        # 6. 初始化 Scheduler（设置并发数 + 启动调度循环）
        bridge.init_scheduler(1)
        await asyncio.sleep(0.5)
        qapp.processEvents()

        # 7. 刷新下载页：从 DB 加载 TaskItem，重建列表
        page.refresh()
        qapp.processEvents()

        # 验证任务行已加载到 UI
        assert item_id in page._item_widgets, "DownloadPage 未加载到任务行"
        widget = page._item_widgets[item_id]
        assert widget._task_item.status == "pending"

        # 8. 通过控制信号触发下载
        bridge._control_signals.start_download.emit([item_id])
        await asyncio.sleep(0.3)
        qapp.processEvents()

        # 9. 等待下载完成（最长 60 秒），期间处理 Qt 事件以接收 WorkerSignals
        item = None
        for _ in range(120):
            qapp.processEvents()
            await asyncio.sleep(0.5)
            item = item_repo.get(item_id)
            assert item is not None
            if item.status in ("completed", "failed"):
                break

        qapp.processEvents()

        # 10. 验证 DB 中任务项状态
        assert item is not None
        assert item.status == "completed", f"下载失败: {item.fail_reason}"
        assert item.local_path is not None

        # 11. 验证 DownloadPage 显示了下载完成状态
        # item_completed 信号应已更新行 widget 状态与状态栏
        assert widget._task_item.status == "completed"
        status_text = page._status_label.text()
        assert "已完成 1" in status_text, f"状态栏未显示完成: {status_text}"

        # 12. 验证文件落盘
        downloaded_file = Path(item.local_path)
        assert downloaded_file.exists()
        assert downloaded_file.stat().st_size > 0

        # 13. 清理下载文件
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
