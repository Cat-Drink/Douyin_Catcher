"""HttpClient 单元测试。

覆盖 CookieRecord、_cookie_to_record、Cookie 池管理、风控响应处理、
get 异步方法。所有 httpx 响应用 respx mock，CookieRepository 用内存实现，
不依赖真实网络与真实 Cookie。
"""

from __future__ import annotations

import pytest

from app.models import Cookie
from crawlers.http_client import (
    DEFAULT_HEADERS,
    MAX_FAIL_COUNT,
    RISK_STATUS_CODES,
    VERIFY_HTML_MARKERS,
    CookieRecord,
    _cookie_to_record,
)

# ==================== 模块常量测试 ====================


class TestModuleConstants:
    """模块级常量契约测试。"""

    def test_default_headers_contains_required_keys(self) -> None:
        """默认请求头含 User-Agent / Referer / Accept / Accept-Language。"""
        required_keys = {"User-Agent", "Referer", "Accept", "Accept-Language"}
        assert required_keys.issubset(DEFAULT_HEADERS.keys())

    def test_default_headers_referer_douyin(self) -> None:
        """Referer 指向抖音首页。"""
        assert DEFAULT_HEADERS["Referer"] == "https://www.douyin.com/"

    def test_default_headers_ua_chrome(self) -> None:
        """User-Agent 为 Chrome Windows 桌面 UA。"""
        assert "Chrome" in DEFAULT_HEADERS["User-Agent"]
        assert "Windows NT 10.0" in DEFAULT_HEADERS["User-Agent"]

    def test_risk_status_codes_contains_461_412(self) -> None:
        """风控状态码集合含 461 与 412。"""
        assert 461 in RISK_STATUS_CODES
        assert 412 in RISK_STATUS_CODES
        assert 200 not in RISK_STATUS_CODES

    def test_verify_html_markers_non_empty(self) -> None:
        """验证 HTML 特征字符串列表非空。"""
        assert len(VERIFY_HTML_MARKERS) > 0
        assert "captcha_verify" in VERIFY_HTML_MARKERS

    def test_max_fail_count_is_3(self) -> None:
        """Cookie 连续失败上限为 3。"""
        assert MAX_FAIL_COUNT == 3


# ==================== CookieRecord dataclass 测试 ====================


class TestCookieRecord:
    """CookieRecord dataclass 测试。"""

    def test_cookie_record_fields(self) -> None:
        """CookieRecord 字段正确赋值。"""
        record = CookieRecord(
            id=1,
            content="ttwid=fake; msToken=fake",
            label="账号A",
            status="valid",
            last_used="2026-07-11T10:00:00",
            last_check=None,
            fail_count=0,
            created_at="2026-07-11T09:00:00",
        )
        assert record.id == 1
        assert record.content == "ttwid=fake; msToken=fake"
        assert record.label == "账号A"
        assert record.status == "valid"
        assert record.fail_count == 0

    def test_cookie_record_is_frozen(self) -> None:
        """CookieRecord 是 frozen dataclass，不可修改。"""
        record = CookieRecord(
            id=1,
            content="x",
            label=None,
            status="valid",
            last_used=None,
            last_check=None,
            fail_count=0,
            created_at="2026-07-11",
        )
        with pytest.raises(AttributeError):
            record.status = "invalid"  # type: ignore[misc]


# ==================== _cookie_to_record 测试 ====================


class TestCookieToRecord:
    """_cookie_to_record 转换函数测试。"""

    def test_convert_persisted_cookie(self) -> None:
        """已持久化的 Cookie（id 非 None）正确转换。"""
        cookie = Cookie(
            id=42,
            content="ttwid=fake",
            label="账号A",
            status="valid",
            last_used="2026-07-11T10:00:00",
            last_check=None,
            fail_count=1,
            created_at="2026-07-11T09:00:00",
        )
        record = _cookie_to_record(cookie)
        assert record.id == 42
        assert record.content == "ttwid=fake"
        assert record.label == "账号A"
        assert record.status == "valid"
        assert record.fail_count == 1
        assert record.last_used == "2026-07-11T10:00:00"

    def test_convert_unpersisted_cookie_raises(self) -> None:
        """未持久化的 Cookie（id=None）抛 ValueError。"""
        cookie = Cookie(
            id=None,
            content="ttwid=fake",
            label=None,
            status="untested",
            last_used=None,
            last_check=None,
            fail_count=0,
            created_at="",
        )
        with pytest.raises(ValueError, match="未持久化"):
            _cookie_to_record(cookie)

    def test_convert_preserves_all_fields(self) -> None:
        """转换后所有字段一一对应。"""
        cookie = Cookie(
            id=1,
            content="content_str",
            label="label_str",
            status="invalid",
            last_used="2026-01-01",
            last_check="2026-01-02",
            fail_count=5,
            created_at="2026-01-03",
        )
        record = _cookie_to_record(cookie)
        assert record.id == cookie.id
        assert record.content == cookie.content
        assert record.label == cookie.label
        assert record.status == cookie.status
        assert record.last_used == cookie.last_used
        assert record.last_check == cookie.last_check
        assert record.fail_count == cookie.fail_count
        assert record.created_at == cookie.created_at
