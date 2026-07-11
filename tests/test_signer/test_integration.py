"""签名算法集成测试。

通过真实抖音 aweme/detail 接口验证 Signer 生成的签名是否被服务端接受。

运行条件：
    - 项目根目录存在 .test_cookie.txt 文件（已被 .gitignore 排除）
    - 文件内容为有效的抖音 Web Cookie 字符串
    - 使用 pytest -m integration 显式启用

安全约定：
    - Cookie 由用户提供，仅存于 .test_cookie.txt，绝不硬编码
    - 测试结束后 Cookie 文件由用户自行删除
    - CI 环境无 Cookie，集成测试自动跳过
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from crawlers.signer import DEFAULT_USER_AGENT, Signer

pytestmark = [pytest.mark.integration, pytest.mark.signer]

# 抖音 aweme/detail 接口
_API_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

# 测试用 aweme_id（使用一个已知存在的公开视频 ID）
_TEST_AWEME_ID = "7646700367584954368"

# Cookie 文件路径（项目根目录，已被 .gitignore 排除）
_COOKIE_PATH = Path(__file__).parent.parent.parent / ".test_cookie.txt"

# 固定业务参数（按接口设计文档 7.1 节 + 浏览器环境参数）
_BASE_PARAMS: dict[str, str] = {
    "aweme_id": _TEST_AWEME_ID,
    "aid": "6383",
    "device_platform": "webapp",
    "channel": "channel_pc_web",
    "version_code": "170400",
    "version_name": "17.4.0",
    "pc_client_type": "1",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "120.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "120.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": "12",
    "device_memory": "16",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "50",
}


def _load_cookie() -> str | None:
    """从 .test_cookie.txt 加载 Cookie，文件不存在时返回 None。"""
    if not _COOKIE_PATH.exists():
        return None
    cookie = _COOKIE_PATH.read_text(encoding="utf-8").strip()
    return cookie or None


def _make_request(cookie: str, params: dict[str, str]) -> httpx.Response:
    """发起带签名的请求到 aweme/detail 接口。"""
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://www.douyin.com/",
        "Cookie": cookie,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    with httpx.Client(headers=headers, timeout=15.0, follow_redirects=True) as client:
        return client.get(_API_URL, params=params)


@pytest.fixture
def test_cookie() -> str:
    """返回测试 Cookie 字符串，无 Cookie 时跳过。"""
    cookie = _load_cookie()
    if cookie is None:
        pytest.skip("未找到 .test_cookie.txt，集成测试跳过（需用户提供 Cookie）")
    return cookie


class TestSignerLiveIntegration:
    """签名算法真实服务端验证。"""

    def test_sign_accepted_by_server(self, test_cookie: str) -> None:
        """Signer.sign() 生成的完整签名被服务端接受（status_code=0）。"""
        signer = Signer(user_agent=DEFAULT_USER_AGENT)
        sign_params = signer.sign(_API_URL, _BASE_PARAMS, user_agent=DEFAULT_USER_AGENT)

        # 验证四键齐全且格式正确
        assert len(sign_params["X-Bogus"]) == 28
        assert len(sign_params["a_bogus"]) == 44
        assert len(sign_params["msToken"]) == 172
        assert sign_params["verifyFp"].startswith("verify_")

        # 合并业务参数 + 签名参数，发起请求
        full_params = {
            **_BASE_PARAMS,
            "X-Bogus": sign_params["X-Bogus"],
            "a_bogus": sign_params["a_bogus"],
            "msToken": sign_params["msToken"],
        }
        resp = _make_request(test_cookie, full_params)

        # HTTP 200 且 status_code=0 表示签名验证通过
        assert resp.status_code == 200, f"HTTP {resp.status_code} - 签名可能被拒绝"
        data = resp.json()
        assert data.get("status_code") == 0, f"签名验证失败: status_code={data.get('status_code')}"

    def test_abogus_is_required(self, test_cookie: str) -> None:
        """仅发 X-Bogus + msToken（不含 a_bogus）会被服务端拒绝。"""
        signer = Signer(user_agent=DEFAULT_USER_AGENT)
        sign_params = signer.sign(_API_URL, _BASE_PARAMS, user_agent=DEFAULT_USER_AGENT)

        # 仅含 X-Bogus + msToken，不含 a_bogus
        partial_params = {
            **_BASE_PARAMS,
            "X-Bogus": sign_params["X-Bogus"],
            "msToken": sign_params["msToken"],
        }
        resp = _make_request(test_cookie, partial_params)

        # 不含 a_bogus 时，服务端返回空响应或非 0 status_code
        # （具体表现可能是 HTTP 200 空体，或 status_code 非 0）
        assert (
            resp.status_code != 200 or not resp.text.strip()
        ), "不含 a_bogus 的请求应被拒绝，但服务端返回了正常响应"
