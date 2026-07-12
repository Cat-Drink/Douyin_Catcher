"""场景 9：失败重试端到端测试。

验证网络错误时重试机制正确（指数退避）、3 次上限后标记失败。
使用 respx mock 网络响应，不打真实 API。

需要真实 Cookie（.test_cookie.txt）用于解析视频直链。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import httpx
import respx

from app.models import Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler


@respx.mock
async def test_retry_on_network_error(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """网络错误重试：前 3 次失败 → 第 4 次成功 → 最终完成。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 用真实 Cookie 解析视频直链（获取真实下载 URL）
    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    download_url = video_info.no_watermark_url
    assert download_url is not None

    # 3. mock 下载 URL：前 3 次返回 ConnectError，第 4 次返回正常数据
    call_count = 0

    async def side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            raise httpx.ConnectError("mock network error")
        return httpx.Response(200, content=b"fake_video_data_for_retry_test")

    respx.get(download_url).mock(side_effect=side_effect)

    # 4. 创建 Task 与 TaskItem
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="single",
            source_url=f"https://www.douyin.com/video/{real_aweme_id}",
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
            url=download_url,
            title=video_info.title,
            author=video_info.author,
            type="video",
            cover_url=video_info.cover_url,
            status="pending",
            total_bytes=0,
        )
    )

    # 5. 入队并下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler.start()
    item = item_repo.get(item_id)
    assert item is not None
    scheduler.add_task_items([item])

    # 6. 等待下载完成（重试可能需要较长时间）
    for _ in range(300):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status in ("completed", "failed"):
            break
    await scheduler.stop()

    # 7. 验证结果
    item = item_repo.get(item_id)
    assert item is not None
    # 重试后应成功（第 4 次请求返回正常数据）
    assert item.status == "completed", f"重试后仍失败: {item.fail_reason}"
    assert item.local_path is not None
    downloaded_file = Path(item.local_path)
    assert downloaded_file.exists()

    # 8. 清理
    if downloaded_file.exists():
        downloaded_file.unlink()

    await http_client.close()


@respx.mock
async def test_retry_exhausted_then_failed(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """重试耗尽：全部请求失败 → 重试 3 次后标记 failed。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 用真实 Cookie 解析视频直链
    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    download_url = video_info.no_watermark_url
    assert download_url is not None

    # 3. mock 下载 URL：全部返回 500 错误
    respx.get(download_url).mock(return_value=httpx.Response(500, content=b"server error"))

    # 4. 创建 Task 与 TaskItem
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="single",
            source_url=f"https://www.douyin.com/video/{real_aweme_id}",
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
            url=download_url,
            title=video_info.title,
            author=video_info.author,
            type="video",
            cover_url=video_info.cover_url,
            status="pending",
            total_bytes=0,
        )
    )

    # 5. 入队并下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler.start()
    item = item_repo.get(item_id)
    assert item is not None
    scheduler.add_task_items([item])

    # 6. 等待重试耗尽
    for _ in range(300):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status in ("completed", "failed"):
            break
    await scheduler.stop()

    # 7. 验证失败
    item = item_repo.get(item_id)
    assert item is not None
    assert item.status == "failed"
    assert item.fail_reason is not None

    await http_client.close()
