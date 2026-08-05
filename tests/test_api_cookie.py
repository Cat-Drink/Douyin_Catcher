"""Cookie API 端点测试（update_last_used 相关）。

测试 test_cookie / test_all_cookies 端点在使用 Cookie 后
是否正确调用了 update_last_used。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import Cookie
from app.repositories import CookieRepository
from backend.state import ctx
from crawlers.cookie_tester import CookieTestResult


@pytest.fixture
def api_client(memory_db):
    """创建带内存数据库和 mock CookieTester 的 FastAPI TestClient。"""
    ctx.conn = memory_db
    ctx.cookie_repo = CookieRepository(memory_db)

    # Mock CookieTester 返回 valid 结果（test_cookie 是 async 方法，必须用 AsyncMock）
    mock_tester = MagicMock()
    mock_tester.test_cookie = AsyncMock(
        return_value=CookieTestResult(
            is_valid=True,
            error_message="",
            user_nickname="测试用户",
        )
    )
    ctx.cookie_tester = mock_tester

    from backend.api.cookie import router

    app = FastAPI()
    app.include_router(router, prefix="/api/cookie")

    client = TestClient(app)
    yield client
    ctx.conn = None
    ctx.cookie_repo = None
    ctx.cookie_tester = None


class TestCookieLastUsedOnTest:
    """测试 test_cookie 端点调用 update_last_used。"""

    def test_test_cookie_updates_last_used(self, api_client):
        """test_cookie 成功后 last_used 应不再是 None。"""
        repo = ctx.cookie_repo
        cid = repo.add(
            Cookie(
                id=None,
                content="ttwid=test123",
                label="测试Cookie",
                status="untested",
            )
        )

        resp = api_client.post(f"/api/cookie/test/{cid}")
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is True

        # 验证 last_used 已更新
        cookie = repo.get_by_id(cid)
        assert cookie is not None
        assert cookie.last_used is not None
        # 格式应为 ISO8601
        assert "T" in cookie.last_used

    def test_test_cookie_updates_last_used_when_invalid(self, api_client):
        """test_cookie 即使失败也应更新 last_used。"""
        repo = ctx.cookie_repo
        cid = repo.add(
            Cookie(
                id=None,
                content="ttwid=bad",
                label="失效Cookie",
                status="untested",
            )
        )

        # 让 mock 返回无效
        ctx.cookie_tester.test_cookie.return_value = CookieTestResult(
            is_valid=False,
            error_message="Cookie 已过期",
            user_nickname=None,
        )

        resp = api_client.post(f"/api/cookie/test/{cid}")
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False

        cookie = repo.get_by_id(cid)
        assert cookie is not None
        # 即使无效，也应该更新 last_used（因为 Cookie 被"使用"过了）
        assert cookie.last_used is not None
        assert cookie.status == "invalid"


class TestCookieLastUsedOnTestAll:
    """测试 test_all_cookies 端点调用 update_last_used。"""

    def test_test_all_updates_last_used_for_each_cookie(self, api_client):
        """test_all 应更新每个被测 Cookie 的 last_used。"""
        repo = ctx.cookie_repo
        c1 = repo.add(
            Cookie(
                id=None,
                content="ttwid=c1",
                label="C1",
                status="valid",
            )
        )
        c2 = repo.add(
            Cookie(
                id=None,
                content="ttwid=c2",
                label="C2",
                status="untested",
            )
        )
        # 这个 invalid 不会被 test_all 测试到
        repo.add(
            Cookie(
                id=None,
                content="ttwid=c3",
                label="C3",
                status="invalid",
            )
        )

        resp = api_client.post("/api/cookie/test-all")
        assert resp.status_code == 200
        results = resp.json()
        # 只测试非 invalid 的
        assert len(results) == 2

        # 验证两个被测 Cookie 的 last_used 都已更新
        cookie1 = repo.get_by_id(c1)
        cookie2 = repo.get_by_id(c2)
        assert cookie1.last_used is not None
        assert cookie2.last_used is not None
