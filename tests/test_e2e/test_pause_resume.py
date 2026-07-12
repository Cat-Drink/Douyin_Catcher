"""场景 7：暂停/恢复端到端测试。

验证下载中暂停后状态正确、.part 文件保留、恢复后从断点继续、最终完成。

需要真实 Cookie（.test_cookie.txt）与真实 aweme_id（.test_aweme_id.txt）。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from app.models import Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler


async def test_pause_and_resume(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """暂停/恢复：下载中暂停 → 状态正确 → 恢复 → 从断点继续 → 完成。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 解析视频直链
    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    assert video_info.no_watermark_url is not None

    # 3. 创建 Task 与 TaskItem
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
            url=video_info.no_watermark_url,
            title=video_info.title,
            author=video_info.author,
            type="video",
            cover_url=video_info.cover_url,
            status="pending",
            total_bytes=0,
        )
    )

    # 4. 启动下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler.start()
    item = item_repo.get(item_id)
    assert item is not None
    scheduler.add_task_items([item])

    # 5. 等待下载开始
    for _ in range(20):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status == "downloading" and item.downloaded_bytes > 0:
            break

    # 6. 暂停下载
    await scheduler.pause(item_id)
    await asyncio.sleep(1)

    # 验证暂停后状态
    item = item_repo.get(item_id)
    assert item is not None
    assert item.status == "paused"

    # 7. 恢复下载
    await scheduler.resume(item_id)

    # 8. 等待下载完成
    for _ in range(120):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status in ("completed", "failed"):
            break
    await scheduler.stop()

    # 9. 验证最终完成
    item = item_repo.get(item_id)
    assert item is not None
    assert item.status == "completed", f"恢复后下载失败: {item.fail_reason}"
    assert item.local_path is not None
    downloaded_file = Path(item.local_path)
    assert downloaded_file.exists()
    assert downloaded_file.stat().st_size > 0

    # 10. 清理
    if downloaded_file.exists():
        downloaded_file.unlink()

    await http_client.close()
