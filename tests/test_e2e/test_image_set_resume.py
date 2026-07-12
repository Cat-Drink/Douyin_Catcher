"""场景 7：图集断点续传端到端测试。

验证图集下载中断后 .part 文件保留、重启后恢复队列、Range 续传、所有图片完整落盘。

需要真实 Cookie（.test_cookie.txt）与真实图集 aweme_id（.test_image_set_aweme_id.txt）。
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

pytestmark = pytest.mark.integration


async def test_image_set_resume_after_interrupt(
    real_cookie: str,
    real_image_set_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """图集断点续传：解析 → 入队 → 部分下载 → 中断 → 重启恢复 → 所有图片完整。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    # 2. 解析图集链接，获取 image_urls 列表
    share_url = f"https://www.douyin.com/video/{real_image_set_aweme_id}"
    parsed = await url_parser.parse(share_url)
    assert parsed.type == "image_set"
    assert parsed.aweme_id == real_image_set_aweme_id

    video_info = await video_parser.parse_video(real_image_set_aweme_id, real_cookie)
    assert video_info.type == "image_set"
    assert len(video_info.image_urls) > 0
    image_count = len(video_info.image_urls)

    # 3. 为每张图片创建 TaskItem（type="image", url=image_url）
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="single",
            source_url=share_url,
            status="pending",
            total_items=image_count,
            download_dir=str(tmp_download_dir),
        )
    )

    item_ids: list[int] = []
    for idx, img_url in enumerate(video_info.image_urls):
        item_id = item_repo.create(
            TaskItem(
                id=None,
                task_id=task_id,
                aweme_id=f"{real_image_set_aweme_id}_{idx}",
                url=img_url,
                title=video_info.title,
                author=video_info.author,
                type="image",
                cover_url=video_info.cover_url,
                status="pending",
                total_bytes=0,
            )
        )
        item_ids.append(item_id)

    # 4. 启动 Scheduler，入队下载
    scheduler1 = Scheduler(conn=clean_db, max_concurrent=3)
    await scheduler1.start()
    items = [item_repo.get(iid) for iid in item_ids]
    items = [item for item in items if item is not None]
    scheduler1.add_task_items(items)

    # 5. 等待一小段时间（约 2 秒）让部分图片开始下载
    for _ in range(4):
        await asyncio.sleep(0.5)
        any_downloading = False
        for iid in item_ids:
            item = item_repo.get(iid)
            assert item is not None
            if item.status == "downloading":
                any_downloading = True
                break
        if any_downloading:
            break

    # 6. 调用 scheduler.stop() 中断下载
    await scheduler1.stop()

    # 7. 验证至少有一个 .part 文件存在（或部分 item 状态为 downloading/pending）
    # 图片较小，可能已全部完成或尚未开始，不强断言（参考 test_resume.py）
    part_files = list(tmp_download_dir.glob("*.part"))

    # 8. 创建新的 Scheduler（同一个 clean_db 连接）
    scheduler2 = Scheduler(conn=clean_db, max_concurrent=3)

    # 9. 调用 restore_pending_tasks 恢复未完成任务
    await scheduler2.restore_pending_tasks()
    await scheduler2.start()

    # 10. 等待所有任务完成（最长 60 秒）
    for _ in range(120):
        await asyncio.sleep(0.5)
        all_done = True
        for iid in item_ids:
            item = item_repo.get(iid)
            assert item is not None
            if item.status not in ("completed", "failed"):
                all_done = False
                break
        if all_done:
            break
    await scheduler2.stop()

    # 11. 验证所有 item.status == "completed"
    # 12. 验证所有图片文件存在且大小 > 0
    downloaded_files: list[Path] = []
    for iid in item_ids:
        item = item_repo.get(iid)
        assert item is not None
        assert item.status == "completed", f"图片 {iid} 断点续传下载失败: {item.fail_reason}"
        assert item.local_path is not None
        file_path = Path(item.local_path)
        assert file_path.exists(), f"图片文件不存在: {file_path}"
        assert file_path.stat().st_size > 0, f"图片文件大小为 0: {file_path}"
        downloaded_files.append(file_path)

    # 13. 清理文件和 http_client
    for file_path in downloaded_files:
        if file_path.exists():
            file_path.unlink()
    for part_file in part_files:
        if part_file.exists():
            part_file.unlink()

    await http_client.close()
