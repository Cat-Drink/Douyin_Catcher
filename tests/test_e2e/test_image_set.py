"""场景 2：图集下载全流程端到端测试。

验证图集类型识别、多图片直链解析、并发下载、所有图片落盘。

需要真实 Cookie（.test_cookie.txt）与真实图集 aweme_id（.test_image_set_aweme_id.txt）。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from app.models import Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler


async def test_image_set_download_full_flow(
    real_cookie: str,
    real_image_set_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """图集下载全流程：解析 → 获取图片直链 → 并发下载 → 所有图片存在。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    # 2. 构造分享链接并解析
    # 注：URLParser 统一把 /video/ 路径归为 'video'，image_set 的最终判定
    # 依赖 VideoParser 调用 detail 接口后的 video_info.type
    share_url = f"https://www.douyin.com/video/{real_image_set_aweme_id}"
    parsed = await url_parser.parse(share_url)
    assert parsed.type == "video"
    assert parsed.aweme_id == real_image_set_aweme_id

    # 3. 解析图集图片直链
    video_info = await video_parser.parse_video(real_image_set_aweme_id, real_cookie)
    assert video_info.type == "image_set"
    assert len(video_info.image_urls) > 0
    image_count = len(video_info.image_urls)

    # 4. 创建 Task 与多个 TaskItem（每张图片一个）
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
                type="image_set",
                cover_url=video_info.cover_url,
                status="pending",
                total_bytes=0,
            )
        )
        item_ids.append(item_id)

    # 5. 入队并启动下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=3)
    await scheduler.start()
    items = [item_repo.get(iid) for iid in item_ids]
    items = [item for item in items if item is not None]
    scheduler.add_task_items(items)

    # 6. 等待所有图片下载完成（最长 120 秒）
    for _ in range(240):
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
    await scheduler.stop()

    # 7. 验证所有图片下载完成
    completed_count = 0
    downloaded_files: list[Path] = []
    for iid in item_ids:
        item = item_repo.get(iid)
        assert item is not None
        assert item.status == "completed", f"图片 {iid} 下载失败: {item.fail_reason}"
        assert item.local_path is not None
        file_path = Path(item.local_path)
        assert file_path.exists()
        assert file_path.stat().st_size > 0
        completed_count += 1
        downloaded_files.append(file_path)

    assert completed_count == image_count

    # 8. 清理
    for file_path in downloaded_files:
        if file_path.exists():
            file_path.unlink()

    await http_client.close()
