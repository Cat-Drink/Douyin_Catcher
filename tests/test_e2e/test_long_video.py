"""场景：长视频下载全流程端到端测试。

验证从链接解析到文件下载的完整链路（针对 duration > 60s 的长视频）：
    分享链接 → URLParser.parse() → VideoParser.parse_video() → Scheduler 下载 → 文件落盘

需要真实 Cookie（.test_cookie.txt）与真实长视频 aweme_id（.test_long_video_aweme_id.txt）。
长视频文件较大，等待下载完成的超时时间放宽至 120 秒。
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
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler

# 标记所有端到端测试为 integration（CI 默认跳过）
pytestmark = pytest.mark.integration


async def test_long_video_download_full_flow(
    real_cookie: str,
    real_long_video_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """长视频下载全流程：解析 → 获取直链 → 下载 → 文件存在。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    # 2. 构造分享链接并解析
    share_url = f"https://www.douyin.com/video/{real_long_video_aweme_id}"
    parsed = await url_parser.parse(share_url)
    assert parsed.type == "video"
    assert parsed.aweme_id == real_long_video_aweme_id

    # 3. 解析视频直链（长视频 type 应为 long_video）
    video_info = await video_parser.parse_video(real_long_video_aweme_id, real_cookie)
    assert video_info.type == "long_video"
    assert video_info.no_watermark_url is not None
    assert video_info.no_watermark_url.startswith("http")

    # 4. 创建 Task 与 TaskItem（type 设为 "video"）
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
            aweme_id=real_long_video_aweme_id,
            url=video_info.no_watermark_url,
            title=video_info.title,
            author=video_info.author,
            type="video",
            cover_url=video_info.cover_url,
            status="pending",
            total_bytes=0,
        )
    )

    # 5. 入队并启动下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler.start()
    item = item_repo.get(item_id)
    assert item is not None
    scheduler.add_task_items([item])

    # 6. 等待下载完成（最长 120 秒，长视频文件较大）
    for _ in range(240):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status in ("completed", "failed"):
            break
    await scheduler.stop()

    # 7. 验证结果
    assert item is not None
    assert item.status == "completed", f"下载失败: {item.fail_reason}"
    assert item.local_path is not None
    downloaded_file = Path(item.local_path)
    assert downloaded_file.exists()
    assert downloaded_file.stat().st_size > 0

    # 8. 清理
    if downloaded_file.exists():
        downloaded_file.unlink()

    # 关闭 http_client
    await http_client.close()
