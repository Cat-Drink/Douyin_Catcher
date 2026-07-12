"""场景 10：Cookie 测试端到端测试。

验证 CookieTester 对有效/失效 Cookie 的测试逻辑与状态更新。

需要真实 Cookie（.test_cookie.txt）。
"""

from __future__ import annotations

import sqlite3

from app.models import Cookie
from app.repositories import CookieRepository
from crawlers.cookie_tester import CookieTester
from crawlers.http_client import HttpClient
from crawlers.signer import Signer


async def test_cookie_validity_check(
    real_cookie: str,
    clean_db: sqlite3.Connection,
) -> None:
    """Cookie 测试：有效 Cookie 标记 valid，失效 Cookie 标记 invalid。"""
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    cookie_tester = CookieTester(http_client, signer)

    # 2. 添加有效 Cookie（untested 状态）
    valid_cookie_id = cookie_repo.add(
        Cookie(
            id=None,
            content=real_cookie,
            label="有效账号",
            status="untested",
            fail_count=0,
            created_at="",
        )
    )

    # 3. 测试有效 Cookie
    result = await cookie_tester.test_cookie(real_cookie)
    assert result.is_valid, f"有效 Cookie 测试失败: {result.error_message}"

    # 4. 验证状态更新
    cookie_repo.update_status(valid_cookie_id, "valid")
    valid_cookie = cookie_repo.get_by_id(valid_cookie_id)
    assert valid_cookie is not None
    assert valid_cookie.status == "valid"

    # 5. 测试失效 Cookie
    invalid_cookie_content = "ttwid=invalid_fake_cookie; msToken=fake_invalid"
    invalid_result = await cookie_tester.test_cookie(invalid_cookie_content)
    assert not invalid_result.is_valid

    # 6. 添加失效 Cookie 并更新状态
    invalid_cookie_id = cookie_repo.add(
        Cookie(
            id=None,
            content=invalid_cookie_content,
            label="失效账号",
            status="untested",
            fail_count=0,
            created_at="",
        )
    )
    cookie_repo.update_status(invalid_cookie_id, "invalid")
    invalid_cookie = cookie_repo.get_by_id(invalid_cookie_id)
    assert invalid_cookie is not None
    assert invalid_cookie.status == "invalid"

    await http_client.close()
