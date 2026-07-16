"""场景 5：用户主页抓取端到端测试。

验证主页链接识别、主页作品列表抓取、作品解析、勾选下载。

需要真实 Cookie（.test_cookie.txt）与真实 sec_user_id（.test_sec_user_id.txt）。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.models import Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.user_home_crawler import HomeFilters, UserHomeCrawler
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler

pytestmark = pytest.mark.integration


async def test_user_home_crawl_and_download(
    real_cookie: str,
    real_sec_user_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """用户主页抓取：解析主页 → 抓取作品列表 → 勾选前 2 个 → 下载完成。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    user_home_crawler = UserHomeCrawler(http_client, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 构造主页链接并解析
    home_url = f"https://www.douyin.com/user/{real_sec_user_id}"
    parsed = await url_parser.parse(home_url)
    assert parsed.type == "user_home"
    assert parsed.sec_user_id == real_sec_user_id

    # 3. 抓取作品列表（最多取前 3 个）
    filters = HomeFilters(type_filter="all", max_count=3)
    posts = []
    async for post in user_home_crawler.fetch_user_posts(real_sec_user_id, filters, real_cookie):
        posts.append(post)
        if len(posts) >= 3:
            break

    assert len(posts) > 0, "未抓取到任何作品"
    for post in posts:
        assert post.aweme_id
        assert post.title is not None
        assert post.cover_url

    # 4. 勾选前 2 个作品，解析直链
    selected_posts = posts[:2]
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="user_home",
            source_url=home_url,
            status="pending",
            total_items=len(selected_posts),
            download_dir=str(tmp_download_dir),
        )
    )

    item_ids: list[int] = []
    for post in selected_posts:
        video_info = await video_parser.parse_video(post.aweme_id, real_cookie)
        download_url = video_info.no_watermark_url or (
            video_info.image_urls[0] if video_info.image_urls else None
        )
        assert download_url is not None, f"作品 {post.aweme_id} 无下载直链"

        item_id = item_repo.create(
            TaskItem(
                id=None,
                task_id=task_id,
                aweme_id=post.aweme_id,
                url=download_url,
                title=video_info.title,
                author=video_info.author,
                type=video_info.type,
                cover_url=video_info.cover_url,
                status="pending",
                total_bytes=0,
            )
        )
        item_ids.append(item_id)

    # 5. 入队并下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=2)
    await scheduler.start()
    items = [item_repo.get(iid) for iid in item_ids]
    items = [item for item in items if item is not None]
    scheduler.add_task_items(items)

    # 6. 等待完成
    for _ in range(180):
        await asyncio.sleep(0.5)
        all_done = all(
            item_repo.get(iid).status in ("completed", "failed")  # type: ignore[union-attr]
            for iid in item_ids
        )
        if all_done:
            break
    await scheduler.stop()

    # 7. 验证下载完成
    downloaded_files: list[Path] = []
    for iid in item_ids:
        item = item_repo.get(iid)
        assert item is not None
        assert item.status == "completed", f"作品 {iid} 下载失败: {item.fail_reason}"
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
