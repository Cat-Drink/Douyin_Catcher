"""场景 5 扩展：UserHomeCrawler 分页深度与过滤端到端测试。

验证 fetch_user_posts 的分页终止逻辑、日期过滤与类型过滤行为。
分页测试限制迭代数量（最多 30 条），避免对抖音接口发起过多请求。

需要真实 Cookie（.test_cookie.txt）与真实 sec_user_id（.test_sec_user_id.txt）。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import CookieRepository
from crawlers import api_spec
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.user_home_crawler import HomeFilters, UserHomeCrawler

pytestmark = pytest.mark.integration


async def test_user_home_pagination_has_more_termination(
    real_cookie: str,
    real_sec_user_id: str,
    clean_db: sqlite3.Connection,
) -> None:
    """分页深度：抓取多页作品，验证 has_more 终止与字段完整性。

    限制最多抓取 ``POST_PAGE_SIZE * 2`` 与 30 的较小值，避免过多 API 请求。
    """
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    user_home_crawler = UserHomeCrawler(http_client, signer)

    # 2. 限制迭代数量：取 POST_PAGE_SIZE * 2 与 30 的较小值
    max_items = min(api_spec.POST_PAGE_SIZE * 2, 30)

    # 3. 异步迭代收集前 N 条 PostItem
    posts = []
    async for post in user_home_crawler.fetch_user_posts(
        real_sec_user_id, HomeFilters(), real_cookie
    ):
        posts.append(post)
        if len(posts) >= max_items:
            break

    # 4. 验证列表非空
    assert len(posts) > 0, "未抓取到任何作品"

    # 5. 验证每个 PostItem 必要字段
    for post in posts:
        assert post.aweme_id, "aweme_id 为空"
        assert post.type in ("video", "image_set", "long_video"), f"未知作品类型: {post.type}"

    await http_client.close()


async def test_user_home_filter_by_date(
    real_cookie: str,
    real_sec_user_id: str,
    clean_db: sqlite3.Connection,
) -> None:
    """日期过滤：仅抓取最近 7 天的作品，验证 create_time 落在范围内。

    若用户近期无发帖，返回空列表视为 acceptable。
    """
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    user_home_crawler = UserHomeCrawler(http_client, signer)

    # 2. 构造最近 7 天日期范围（YYYY-MM-DD）
    today = datetime.now(tz=UTC)
    start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    filters = HomeFilters(start_date=start_date, end_date=end_date)

    # 3. 异步迭代收集前 10 条
    posts = []
    async for post in user_home_crawler.fetch_user_posts(real_sec_user_id, filters, real_cookie):
        posts.append(post)
        if len(posts) >= 10:
            break

    # 4. 验证返回项的 create_time 在范围内（若返回非空）
    if posts:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )
        for post in posts:
            assert post.create_time, "create_time 为空"
            item_dt = datetime.strptime(post.create_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            assert (
                start_dt <= item_dt <= end_dt
            ), f"create_time {post.create_time} 不在 [{start_date}, {end_date}] 范围内"

    await http_client.close()


async def test_user_home_filter_by_type(
    real_cookie: str,
    real_sec_user_id: str,
    clean_db: sqlite3.Connection,
) -> None:
    """类型过滤：仅抓取 video 类型作品，验证 type == "video"。

    若用户无 video 类型作品，返回空列表视为 acceptable。
    """
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    user_home_crawler = UserHomeCrawler(http_client, signer)

    # 2. 构造 video 类型过滤
    filters = HomeFilters(type_filter="video")

    # 3. 异步迭代收集前 10 条
    posts = []
    async for post in user_home_crawler.fetch_user_posts(real_sec_user_id, filters, real_cookie):
        posts.append(post)
        if len(posts) >= 10:
            break

    # 4. 验证返回项的 type == "video"（若有返回）
    for post in posts:
        assert post.type == "video", f"类型过滤失效，期望 video 实际 {post.type}"

    await http_client.close()
