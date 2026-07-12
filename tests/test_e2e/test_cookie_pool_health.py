"""场景：Cookie 池健康检查完整流程端到端测试。

验证 Cookie 池从健康检查到下载完成的完整链路：
    注入多 Cookie → CookieTester.test_all() 批量测试 → 标记失效 Cookie →
    解析分享链接 → 解析视频直链 → Scheduler 下载 → 验证使用有效 Cookie

比 ``test_cookie_pool.py`` 更全面：显式调用 CookieTester 进行健康检查、
验证测试结果与状态更新、增加分享链接解析步骤，并确认下载过程使用有效 Cookie。

需要真实 Cookie（.test_cookie.txt）与真实 aweme_id（.test_aweme_id.txt）。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.models import Cookie, Task, TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.cookie_tester import CookieTester
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler

pytestmark = pytest.mark.integration


async def test_cookie_pool_health_check_full_flow(
    real_cookie: str,
    real_aweme_id: str,
    tmp_download_dir: Path,
    clean_db: sqlite3.Connection,
) -> None:
    """Cookie 池健康检查完整流程：批量测试 → 标记失效 → 解析直链 → 下载完成。"""
    # 1. 注入 2 个 Cookie（1 个真实有效，1 个伪造无效），均标记 valid 入池
    cookie_repo = CookieRepository(clean_db)
    valid_cookie_id = cookie_repo.add(
        Cookie(
            id=None,
            content=real_cookie,
            label="真实账号",
            status="valid",
            fail_count=0,
            created_at="",
        )
    )
    invalid_cookie_id = cookie_repo.add(
        Cookie(
            id=None,
            content="invalid_cookie_content_12345",
            label="伪造账号",
            status="valid",
            fail_count=0,
            created_at="",
        )
    )

    # 2. 组装依赖：Signer / HttpClient / URLParser / VideoParser / CookieTester
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)
    cookie_tester = CookieTester(http_client, signer)

    # 3. 调用 CookieTester.test_all() 批量测试所有 Cookie
    cookies_to_test: list[tuple[int, str]] = [
        (valid_cookie_id, real_cookie),
        (invalid_cookie_id, "invalid_cookie_content_12345"),
    ]
    test_results = await cookie_tester.test_all(cookies_to_test)
    result_map = dict(test_results)

    # 4. 验证测试结果：真实 Cookie 有效，伪造 Cookie 无效
    assert result_map[valid_cookie_id].is_valid is True
    assert result_map[invalid_cookie_id].is_valid is False

    # 5. CookieTester 不自动更新 CookieRepository 状态，手动标记失效 Cookie
    cookie_repo.update_status(invalid_cookie_id, "invalid")

    # 6. 解析分享链接 + 视频直链（使用有效 Cookie）
    share_url = f"https://www.douyin.com/video/{real_aweme_id}"
    parsed = await url_parser.parse(share_url)
    assert parsed.type == "video"
    assert parsed.aweme_id == real_aweme_id

    video_info = await video_parser.parse_video(real_aweme_id, real_cookie)
    assert video_info.no_watermark_url is not None
    assert video_info.no_watermark_url.startswith("http")

    # 7. 创建 Task 与 TaskItem
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

    # 8. 入队并下载（Scheduler 使用 Cookie 池）
    scheduler = Scheduler(conn=clean_db, max_concurrent=1)
    await scheduler.start()
    item = item_repo.get(item_id)
    assert item is not None
    scheduler.add_task_items([item])

    # 9. 等待下载完成（最长 60 秒）
    for _ in range(120):
        await asyncio.sleep(0.5)
        item = item_repo.get(item_id)
        assert item is not None
        if item.status in ("completed", "failed"):
            break
    await scheduler.stop()

    # 10. 验证下载成功
    assert item is not None
    assert item.status == "completed", f"Cookie 池健康检查下载失败: {item.fail_reason}"
    assert item.local_path is not None
    downloaded_file = Path(item.local_path)
    assert downloaded_file.exists()
    assert downloaded_file.stat().st_size > 0

    # 11. 验证 HttpClient Cookie 池仅返回有效 Cookie（失效 Cookie 已被排除）
    pooled_cookie = cookie_repo.get_valid()
    assert pooled_cookie is not None
    assert pooled_cookie.id == valid_cookie_id
    stale_cookie = cookie_repo.get_by_id(invalid_cookie_id)
    assert stale_cookie is not None
    assert stale_cookie.status == "invalid"

    # 12. 清理文件与 http_client
    if downloaded_file.exists():
        downloaded_file.unlink()

    await http_client.close()
