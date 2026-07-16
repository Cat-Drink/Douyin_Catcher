"""场景 4：文件导入下载端到端测试。

验证从 txt 文件读取链接列表、批量解析、下载完成。

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

pytestmark = pytest.mark.integration


async def test_file_import_download(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    """文件导入下载：从 txt 文件读取链接，批量解析与下载。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 创建临时 txt 文件（含链接、空行、注释行）
    share_url = f"https://www.douyin.com/video/{real_aweme_id}"
    links_file = tmp_path / "links.txt"
    links_file.write_text(
        f"{share_url}\n"  # 有效链接
        "\n"  # 空行（应跳过）
        f"# 这是注释\n"  # 注释行（应跳过）
        f"{share_url}\n",  # 有效链接
        encoding="utf-8",
    )

    # 3. 模拟 UI 读取 txt 文件，逐行解析
    lines = links_file.read_text(encoding="utf-8").splitlines()
    valid_urls: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        valid_urls.append(line)

    assert len(valid_urls) == 2

    # 4. 批量解析视频直链
    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    assert video_info.no_watermark_url is not None

    # 5. 创建 Task 与 TaskItem
    task_repo = TaskRepository(clean_db)
    item_repo = TaskItemRepository(clean_db)
    task_id = task_repo.create(
        Task(
            id=None,
            source_type="file_import",
            source_url=str(links_file),
            status="pending",
            total_items=len(valid_urls),
            download_dir=str(tmp_download_dir),
        )
    )

    item_ids: list[int] = []
    for i in range(len(valid_urls)):
        item_id = item_repo.create(
            TaskItem(
                id=None,
                task_id=task_id,
                aweme_id=f"{real_aweme_id}_import_{i}",
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

    # 6. 入队并下载
    scheduler = Scheduler(conn=clean_db, max_concurrent=2)
    await scheduler.start()
    items = [item_repo.get(iid) for iid in item_ids]
    items = [item for item in items if item is not None]
    scheduler.add_task_items(items)

    # 7. 等待完成
    for _ in range(120):
        await asyncio.sleep(0.5)
        all_done = all(
            item_repo.get(iid).status in ("completed", "failed")  # type: ignore[union-attr]
            for iid in item_ids
        )
        if all_done:
            break
    await scheduler.stop()

    # 8. 验证全部完成
    downloaded_files: list[Path] = []
    for iid in item_ids:
        item = item_repo.get(iid)
        assert item is not None
        assert item.status == "completed", f"导入项 {iid} 下载失败: {item.fail_reason}"
        assert item.local_path is not None
        file_path = Path(item.local_path)
        assert file_path.exists()
        assert file_path.stat().st_size > 0
        downloaded_files.append(file_path)

    # 9. 清理
    for file_path in downloaded_files:
        if file_path.exists():
            file_path.unlink()

    await http_client.close()
