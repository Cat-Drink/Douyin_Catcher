"""不依赖真实 Cookie 的全链路 mock 集成测试。

用 respx mock 下载 CDN 响应，跑通 DownloadBridge -> Scheduler -> Downloader
完整链路，验证 item_completed 信号触发与文件落盘。

与 ``tests/test_e2e/test_download_bridge_e2e.py`` 的区别：
    - 不标记 ``@pytest.mark.integration``，CI 可跑
    - 不依赖真实 Cookie / 真实 aweme_id / 真实网络
    - TaskItem.url 预填（跳过 VideoParser 直链解析），下载字节用 respx mock

调用链覆盖::

    control_signals.start_download.emit([item_id])
      -> DownloadBridge._do_start_download
      -> Scheduler.add_task_items -> _run_download -> Downloader.download
      -> respx mock CDN 返回字节流 -> 文件落盘
      -> on_item_completed 回调 -> worker_signals.item_completed.emit

参考：``tests/test_e2e/test_download_bridge_e2e.py``（真实全链路骨架）、
      ``tests/test_scheduler.py``（respx mock 下载字节模式）。
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import respx

from app import database
from app.models import Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from downloader.scheduler import Scheduler
from worker.async_worker import AsyncWorker
from worker.download_bridge import DownloadBridge
from worker.signals import ControlSignals, WorkerSignals

# mock 下载 CDN 固定 URL（与 test_scheduler.py 一致，便于 respx 匹配）
_DOWNLOAD_URL = "https://cdn.example.com/mock_video.mp4"
_MOCK_VIDEO_DATA = b"mock_video_binary_data_for_ci"

# 轮询等待下载完成的最大次数与间隔
_POLL_ROUNDS = 60
_POLL_INTERVAL = 0.5


@respx.mock
async def test_download_bridge_full_link_mock(
    qapp,
    async_worker: AsyncWorker,
    tmp_path: Path,
) -> None:
    """DownloadBridge 全链路 mock 测试：预填 url -> 启动下载 -> 完成 -> 文件落盘。

    预填 ``TaskItem.url`` 跳过 VideoParser 直链解析，下载字节由 respx mock
    返回，验证 DownloadBridge -> Scheduler -> Downloader 完整链路畅通。

    注意：使用文件数据库（``check_same_thread=False``）而非内存 DB，因为
    ``AsyncWorker`` 在独立 QThread 中运行，``TaskItemRepository`` 跨线程
    访问连接时内存 DB 默认 ``check_same_thread=True`` 会报错。

    Args:
        qapp: pytest-qt 提供的 QApplication（DownloadBridge 是 QObject）。
        async_worker: 真实 AsyncWorker（conftest fixture，已 start）。
        tmp_path: 临时目录（pytest 内置，用于 DB 文件与下载目录）。
    """
    # 0. 创建文件数据库（check_same_thread=False，允许 AsyncWorker 线程跨线程访问）
    db_path = tmp_path / "test_mock.db"
    conn = database.get_connection(db_path)
    database.init_db(conn)
    try:
        # 1. mock CDN：head 返回 404 触发普通流式下载，get 返回视频字节
        respx.head(_DOWNLOAD_URL).mock(return_value=httpx.Response(404))
        respx.get(_DOWNLOAD_URL).mock(
            return_value=httpx.Response(
                200,
                content=_MOCK_VIDEO_DATA,
                headers={"Content-Length": str(len(_MOCK_VIDEO_DATA))},
            )
        )

        # 2. 创建 Task 与 TaskItem（url 预填，跳过直链解析）
        task_repo = TaskRepository(conn)
        item_repo = TaskItemRepository(conn)
        cookie_repo = CookieRepository(conn)  # 预填 url 时不会被使用
        task_id = task_repo.create(
            Task(
                id=None,
                source_type="single",
                source_url="https://www.douyin.com/video/mock_aweme_001",
                status="pending",
                total_items=1,
                download_dir=str(tmp_path),
            )
        )
        item_id = item_repo.create(
            TaskItem(
                id=None,
                task_id=task_id,
                aweme_id="mock_aweme_001",
                url=_DOWNLOAD_URL,
                title="CI mock 测试视频",
                author="mock 作者",
                type="video",
                cover_url="https://cdn.example.com/cover.jpg",
                status="pending",
                total_bytes=0,
            )
        )

        # 3. 组装真实 Scheduler + DownloadBridge（video_parser 用 MagicMock 占位，
        #    预填 url 时不会被调用）
        scheduler = Scheduler(conn=conn, max_concurrent=1)
        worker_signals = WorkerSignals()
        control_signals = ControlSignals()
        bridge = DownloadBridge(
            async_worker=async_worker,
            scheduler=scheduler,
            task_item_repository=item_repo,
            task_repository=task_repo,
            worker_signals=worker_signals,
            control_signals=control_signals,
            video_parser=MagicMock(),
            cookie_repository=cookie_repo,
        )

        # 4. 监听 item_completed 信号
        received_completed: list[int] = []
        worker_signals.item_completed.connect(lambda tid: received_completed.append(tid))

        # 5. 初始化 Scheduler（设置并发数 + 启动调度循环）
        bridge.init_scheduler(1)
        await asyncio.sleep(0.5)
        qapp.processEvents()

        # 6. 通过控制信号启动下载
        bridge._control_signals.start_download.emit([item_id])  # noqa: SLF001
        await asyncio.sleep(0.3)
        qapp.processEvents()

        # 7. 轮询等待下载完成
        item = None
        for _ in range(_POLL_ROUNDS):
            qapp.processEvents()
            await asyncio.sleep(_POLL_INTERVAL)
            item = item_repo.get(item_id)
            assert item is not None
            if item.status in ("completed", "failed"):
                break

        qapp.processEvents()

        # 8. 验证结果
        assert item is not None
        assert item.status == "completed", f"下载失败: {item.fail_reason}"
        assert received_completed == [item_id], "item_completed 信号未正确触发"
        assert item.local_path is not None, "local_path 未回填"
        downloaded_file = Path(item.local_path)
        assert downloaded_file.exists(), f"下载文件不存在: {downloaded_file}"
        assert downloaded_file.stat().st_size > 0, "下载文件为空"
        # 清理下载文件
        downloaded_file.unlink(missing_ok=True)
    finally:
        # 停止 Scheduler：必须在 async_worker.stop() 之前在 worker 线程内关闭
        if async_worker.isRunning():
            with contextlib.suppress(Exception):
                async_worker.submit(scheduler.stop()).result(timeout=10)
        with contextlib.suppress(sqlite3.Error):
            conn.close()
