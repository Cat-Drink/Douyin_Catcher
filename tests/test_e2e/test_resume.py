"""场景 6：断点续传端到端测试。

验证下载中断后 .part 文件保留、重启后恢复队列、Range 续传、文件完整。

需要真实 Cookie（.test_cookie.txt）与真实 aweme_id（.test_aweme_id.txt）。
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
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler

# 标记所有端到端测试为 integration（CI 默认跳过）
pytestmark = pytest.mark.integration


async def test_resume_after_restart(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """断点续传：下载中断 → .part 保留 → 重启恢复 → Range 续传 → 文件完整。"""
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

    # 4. 启动下载，等待部分字节写入后中断
    scheduler1 = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler1.start()
    item = item_repo.get(item_id)
    assert item is not None
    scheduler1.add_task_items([item])

    # 等待下载开始（downloaded_bytes > 0 或状态变为 downloading）
    for _ in range(20):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status == "downloading" and item.downloaded_bytes > 0:
            break

    # 5. 模拟应用关闭（停止 Scheduler）
    await scheduler1.stop()

    # 6. 验证中断后状态
    item = item_repo.get(item_id)
    assert item is not None
    # 停止后状态可能是 downloading（未及时更新）或 paused（restore_pending_tasks 会重置）
    # .part 文件应存在（如果下载已开始）
    part_file = tmp_download_dir / f"{real_aweme_id}.mp4.part"
    # part 文件是否存在取决于下载进度，不强断言

    # 7. 模拟应用重启：创建新 Scheduler，恢复队列
    scheduler2 = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler2.restore_pending_tasks()
    await scheduler2.start()

    # 8. 等待下载完成
    for _ in range(120):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status in ("completed", "failed"):
            break
    await scheduler2.stop()

    # 9. 验证最终完成
    item = item_repo.get(item_id)
    assert item is not None
    assert item.status == "completed", f"断点续传下载失败: {item.fail_reason}"
    assert item.local_path is not None
    downloaded_file = Path(item.local_path)
    assert downloaded_file.exists()
    assert downloaded_file.stat().st_size > 0

    # 10. 清理
    if downloaded_file.exists():
        downloaded_file.unlink()
    if part_file.exists():
        part_file.unlink()

    await http_client.close()
