"""场景 3：批量链接下载端到端测试。

验证多个链接批量解析、批量入队、并发下载、全部完成。

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


async def test_batch_links_download(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """批量链接下载：多个相同链接批量解析与下载。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 批量解析（使用同一 aweme_id 构造 2 个链接）
    share_url = f"https://www.douyin.com/video/{real_aweme_id}"
    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    assert video_info.no_watermark_url is not None

    # 3. 创建批量 Task
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="batch",
            source_url=share_url,
            status="pending",
            total_items=2,
            download_dir=str(tmp_download_dir),
        )
    )

    # 4. 批量创建 TaskItem
    item_ids: list[int] = []
    for i in range(2):
        item_id = item_repo.create(
            TaskItem(
                id=None,
                task_id=task_id,
                aweme_id=f"{real_aweme_id}_batch_{i}",
                url=video_info.no_watermark_url,
                title=f"{video_info.title}_{i}",
                author=video_info.author,
                type="video",
                cover_url=video_info.cover_url,
                status="pending",
                total_bytes=0,
            )
        )
        item_ids.append(item_id)

    # 5. 批量入队并下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=2)
    await scheduler.start()
    items = [item_repo.get(iid) for iid in item_ids]
    items = [item for item in items if item is not None]
    scheduler.add_task_items(items)

    # 6. 等待全部完成
    for _ in range(120):
        await asyncio.sleep(0.5)
        all_done = all(
            item_repo.get(iid).status in ("completed", "failed")  # type: ignore[union-attr]
            for iid in item_ids
        )
        if all_done:
            break
    await scheduler.stop()

    # 7. 验证全部下载完成
    downloaded_files: list[Path] = []
    for iid in item_ids:
        item = item_repo.get(iid)
        assert item is not None
        assert item.status == "completed", f"批量项 {iid} 下载失败: {item.fail_reason}"
        assert item.local_path is not None
        file_path = Path(item.local_path)
        assert file_path.exists()
        assert file_path.stat().st_size > 0
        downloaded_files.append(file_path)

    # 8. 清理
    for file_path in downloaded_files:
        if file_path.exists():
            file_path.unlink()

    await http_client.close()
