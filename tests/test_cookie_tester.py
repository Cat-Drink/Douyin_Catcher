"""CookieTester 单元测试。

覆盖场景:
    - test_cookie 有效 Cookie（status_code=0）
    - test_cookie 无效 Cookie（HTTP 461 由 HttpClient 抛出）
    - test_cookie status_code != 0 业务错误
    - test_cookie 触发安全验证（VerifyRequiredError）
    - test_cookie 触发限流（RateLimitedError）
    - test_cookie 网络异常（NetworkError）
    - test_cookie 响应非 JSON
    - user_nickname 提取（顶层字段 / user.nickname 嵌套 / 缺失）
    - test_all 批量测试
    - _build_test_params / _extract_user_nickname 纯单元测试

测试通过 AsyncMock + MagicMock 模拟 HttpClient，不打真实网络。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from crawlers import api_spec
from crawlers.cookie_tester import CookieTester, CookieTestResult
from crawlers.exceptions import (
    CookieInvalidError,
    NetworkError,
    RateLimitedError,
    VerifyRequiredError,
)

# ==================== fixtures ====================


@pytest.fixture
def mock_http_client() -> MagicMock:
    """返回 mock HttpClient，get 方法为 AsyncMock 供 await 调用。"""
    client = MagicMock(name="HttpClient")
    client.get = AsyncMock(name="HttpClient.get")
    return client


@pytest.fixture
def mock_signer() -> MagicMock:
    """返回 mock Signer（CookieTester 不直接调用，占位注入）。"""
    return MagicMock(name="Signer")


@pytest.fixture
def cookie_tester(mock_http_client: MagicMock, mock_signer: MagicMock) -> CookieTester:
    """返回注入 mock 的 CookieTester 实例。"""
    return CookieTester(mock_http_client, mock_signer)


def _make_response(payload: dict, status_code: int = 200) -> httpx.Response:
    """构造 JSON 响应 httpx.Response。"""
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", api_spec.GENERAL_SEARCH_URL),
    )


# ==================== test_cookie 主流程测试 ====================


class TestTestCookie:
    """test_cookie 主流程测试。"""

    async def test_valid_cookie(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """有效 Cookie：status_code=0 → is_valid=True，error_message=""。"""
        mock_http_client.get.return_value = _make_response({"status_code": 0})
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is True
        assert result.error_message == ""
        # search/single 响应不含昵称字段 → None
        assert result.user_nickname is None
        # 验证调用参数：use_cookie_pool=False + 显式 cookie
        mock_http_client.get.assert_awaited_once()
        call_kwargs = mock_http_client.get.await_args.kwargs
        assert call_kwargs["use_cookie_pool"] is False
        assert call_kwargs["cookie"] == "ttwid=fake"
        assert call_kwargs["params"]["keyword"] == "test"

    async def test_invalid_cookie_461(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """无效 Cookie（HTTP 461 → CookieInvalidError 由 HttpClient 抛出）。"""
        mock_http_client.get.side_effect = CookieInvalidError("Cookie 失效")
        result = await cookie_tester.test_cookie("ttwid=expired")
        assert result.is_valid is False
        assert "失效" in result.error_message
        assert result.user_nickname is None

    async def test_invalid_cookie_429(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """触发限流（HTTP 429 → RateLimitedError）。"""
        mock_http_client.get.side_effect = RateLimitedError("限流")
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is False
        assert "频繁" in result.error_message

    async def test_invalid_cookie_verify_html(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """触发安全验证（VerifyRequiredError）。"""
        mock_http_client.get.side_effect = VerifyRequiredError("需验证")
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is False
        assert "验证" in result.error_message

    async def test_network_error_returns_invalid(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """网络异常 → is_valid=False，error_message 含"网络"。"""
        mock_http_client.get.side_effect = NetworkError("连接超时")
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is False
        assert "网络" in result.error_message

    async def test_status_code_nonzero(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """status_code != 0 → is_valid=False，error_message 为 status_msg。"""
        mock_http_client.get.return_value = _make_response(
            {"status_code": 8, "status_msg": "需要登录"}
        )
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is False
        assert result.error_message == "需要登录"

    async def test_status_code_nonzero_no_status_msg(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """status_code != 0 且无 status_msg → 默认"未知错误"。"""
        mock_http_client.get.return_value = _make_response({"status_code": 8})
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is False
        assert result.error_message == "未知错误"

    async def test_response_not_json(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """响应非 JSON → is_valid=False，error_message 含"网络异常"。"""
        response = MagicMock(spec=httpx.Response)
        response.json.side_effect = ValueError("not json")
        mock_http_client.get.return_value = response
        result = await cookie_tester.test_cookie("ttwid=fake")
        assert result.is_valid is False
        assert "网络异常" in result.error_message


# ==================== user_nickname 提取测试 ====================


class TestExtractUserNickname:
    """_extract_user_nickname 昵称提取测试。"""

    def test_extract_nickname_top_level(self) -> None:
        """顶层 user_nickname 字段。"""
        assert CookieTester._extract_user_nickname({"user_nickname": "alice"}) == "alice"

    def test_extract_nickname_nested_user(self) -> None:
        """user.nickname 嵌套字段。"""
        assert CookieTester._extract_user_nickname({"user": {"nickname": "bob"}}) == "bob"

    def test_extract_nickname_none_when_absent(self) -> None:
        """无昵称字段 → None。"""
        assert CookieTester._extract_user_nickname({}) is None

    def test_extract_nickname_empty_string(self) -> None:
        """空字符串昵称 → None。"""
        assert CookieTester._extract_user_nickname({"user_nickname": ""}) is None

    def test_extract_nickname_non_string(self) -> None:
        """非字符串类型 → None。"""
        assert CookieTester._extract_user_nickname({"user_nickname": 123}) is None

    def test_extract_nickname_top_level_priority(self) -> None:
        """顶层字段优先于嵌套字段。"""
        payload = {"user_nickname": "top", "user": {"nickname": "nested"}}
        assert CookieTester._extract_user_nickname(payload) == "top"


# ==================== _build_test_params 单元测试 ====================


class TestBuildTestParams:
    """_build_test_params 参数构造测试。"""

    def test_build_params_contains_keyword(self) -> None:
        """含 keyword=test。"""
        params = CookieTester._build_test_params()
        assert params["keyword"] == api_spec.COOKIE_TEST_SEARCH_KEYWORD

    def test_build_params_contains_count_offset(self) -> None:
        """含 count 与 offset。"""
        params = CookieTester._build_test_params()
        assert params["count"] == str(api_spec.COOKIE_TEST_SEARCH_COUNT)
        assert params["offset"] == str(api_spec.COOKIE_TEST_SEARCH_OFFSET)

    def test_build_params_contains_common_fixed(self) -> None:
        """含所有 COMMON_FIXED_PARAMS 字段。"""
        params = CookieTester._build_test_params()
        for key, value in api_spec.COMMON_FIXED_PARAMS.items():
            assert params[key] == value


# ==================== test_all 批量测试 ====================


class TestTestAll:
    """test_all 批量测试。"""

    async def test_test_all_multiple_cookies(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """批量测试多个 Cookie，返回顺序与输入一致。"""
        # 模拟两次调用返回不同响应
        mock_http_client.get.side_effect = [
            _make_response({"status_code": 0}),
            _make_response({"status_code": 1, "status_msg": "失效"}),
            _make_response({"status_code": 0}),
        ]
        results = await cookie_tester.test_all(
            [
                (1, "cookie_1"),
                (2, "cookie_2"),
                (3, "cookie_3"),
            ]
        )
        assert len(results) == 3
        assert results[0][0] == 1
        assert results[0][1].is_valid is True
        assert results[1][0] == 2
        assert results[1][1].is_valid is False
        assert results[1][1].error_message == "失效"
        assert results[2][0] == 3
        assert results[2][1].is_valid is True

    async def test_test_all_empty_list(
        self, cookie_tester: CookieTester, mock_http_client: MagicMock
    ) -> None:
        """空列表 → 空结果，不调用 HttpClient。"""
        results = await cookie_tester.test_all([])
        assert results == []
        mock_http_client.get.assert_not_awaited()


# ==================== CookieTestResult 数据结构测试 ====================


class TestCookieTestResult:
    """CookieTestResult dataclass 测试。"""

    def test_valid_result(self) -> None:
        """有效结果字段。"""
        result = CookieTestResult(is_valid=True, error_message="", user_nickname="alice")
        assert result.is_valid is True
        assert result.error_message == ""
        assert result.user_nickname == "alice"

    def test_invalid_result(self) -> None:
        """无效结果字段。"""
        result = CookieTestResult(is_valid=False, error_message="失效", user_nickname=None)
        assert result.is_valid is False
        assert result.error_message == "失效"
        assert result.user_nickname is None

    def test_result_is_frozen(self) -> None:
        """frozen dataclass 不可变（FrozenInstanceError 继承自 AttributeError）。"""
        result = CookieTestResult(is_valid=True, error_message="", user_nickname=None)
        with pytest.raises(AttributeError):
            result.is_valid = False  # type: ignore[misc]
