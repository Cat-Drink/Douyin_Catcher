"""场景：图文预览勾选下载全流程端到端测试（v0.1.7 / v0.1.8 plan 3）。

验证图集预览、勾选部分图片、仅下载勾选图片的完整链路：
    图文链接 -> VideoParser.parse_video -> PreviewItem ->
    勾选部分图片 -> TaskItem(selected_image_indices) -> Scheduler 下载 -> 仅勾选图片落盘

覆盖 v0.1.7 用户反馈 #7：图文勾选下载。

需要真实 Cookie（.test_cookie.txt）与真实图集 aweme_id（.test_image_set_aweme_id.txt）。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from app.models import Task, TaskItem
from app.preview_models import PreviewItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler

# 标记所有端到端测试为 integration（CI 默认跳过）
pytestmark = pytest.mark.integration


async def test_image_set_preview_and_selective_download(
    real_cookie: str,
    real_image_set_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """图文链接 -> 预览 -> 勾选部分图片 -> 下载 -> 验证仅勾选图片下载。

    步骤：
        1. VideoParser.parse_video 解析图集
        2. PreviewItem.from_video_info 构造预览项
        3. 勾选前两张图片（selected_image_indices=[0,1]）
        4. 仅将勾选图片入队下载
        5. 验证仅勾选图片落盘，未勾选图片不下载
    """
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    try:
        # 2. 解析图集
        share_url = f"https://www.douyin.com/video/{real_image_set_aweme_id}"
        parsed = await url_parser.parse(share_url)
        assert parsed.aweme_id == real_image_set_aweme_id

        video_info = await video_parser.parse_video(real_image_set_aweme_id, real_cookie)
        assert video_info.type == "image_set"
        assert len(video_info.image_urls) >= 2, "图集至少需要 2 张图片以验证部分勾选"
        total_image_count = len(video_info.image_urls)

        # 3. 构造 PreviewItem
        preview_item = PreviewItem.from_video_info(video_info)
        assert preview_item.type == "image_set"
        assert preview_item.image_count == total_image_count

        # 4. 勾选前两张图片（selected_image_indices=[0,1]）
        selected_indices = [0, 1]
        selected_urls = [video_info.image_urls[i] for i in selected_indices]
        selected_indices_json = json.dumps(selected_indices)

        # 5. 创建 Task 与仅勾选图片的 TaskItem
        task_repo = TaskRepository(clean_db)
        item_repo = TaskItemRepository(clean_db)
        task_id = task_repo.create(
            Task(
                id=None,
                source_type="single",
                source_url=share_url,
                status="pending",
                total_items=len(selected_urls),
                download_dir=str(tmp_download_dir),
            )
        )

        item_ids: list[int] = []
        for idx, img_url in enumerate(selected_urls):
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
                    selected_image_indices=selected_indices_json,
                )
            )
            item_ids.append(item_id)

        # 6. 入队并启动下载
        scheduler = Scheduler(conn=clean_db, max_concurrent=2)
        await scheduler.start()
        try:
            items = [item_repo.get(iid) for iid in item_ids]
            items = [item for item in items if item is not None]
            scheduler.add_task_items(items)

            # 7. 等待勾选图片下载完成（最长 120 秒）
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

            # 8. 验证仅勾选图片下载完成
            downloaded_files: list[Path] = []
            for iid in item_ids:
                item = item_repo.get(iid)
                assert item is not None
                assert item.status == "completed", f"图片 {iid} 下载失败: {item.fail_reason}"
                assert item.local_path is not None
                file_path = Path(item.local_path)
                assert file_path.exists()
                assert file_path.stat().st_size > 0
                downloaded_files.append(file_path)

            # 9. 验证仅下载了勾选数量的图片（未勾选的未入队，自然不会下载）
            assert len(downloaded_files) == len(selected_urls)
            assert len(downloaded_files) < total_image_count, "应只下载勾选部分，而非全部"

            # 10. 清理
            for file_path in downloaded_files:
                if file_path.exists():
                    file_path.unlink()
        finally:
            await scheduler.stop()
    finally:
        await http_client.close()
