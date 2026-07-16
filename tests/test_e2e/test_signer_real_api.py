"""签名算法真实 API 有效性验证端到端测试。

通过真实抖音 aweme/detail 接口验证 Signer 生成的签名是否被服务端接受。
与 tests/test_signer/test_integration.py 类似，但作为端到端测试流程的一部分。

需要真实 Cookie（.test_cookie.txt）。
"""

from __future__ import annotations

import httpx
import pytest

from crawlers.signer import DEFAULT_USER_AGENT, Signer

pytestmark = pytest.mark.integration

# 抖音 aweme/detail 接口
_API_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

# 测试用 aweme_id（使用一个已知存在的公开视频 ID）
_TEST_AWEME_ID = "7646700367584954368"

# 固定业务参数
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


async def test_signer_valid_against_real_api(real_cookie: str) -> None:
    """签名算法有效性验证：Signer.sign() 生成的签名被服务端接受。"""
    signer = Signer(user_agent=DEFAULT_USER_AGENT)
    sign_params = signer.sign(_API_URL, _BASE_PARAMS, user_agent=DEFAULT_USER_AGENT)

    # 1. 验证四键齐全且格式正确
    assert len(sign_params["X-Bogus"]) == 28
    assert len(sign_params["a_bogus"]) == 44
    assert len(sign_params["msToken"]) == 172
    assert sign_params["verifyFp"].startswith("verify_")

    # 2. 合并业务参数 + 签名参数，发起请求
    full_params = {
        **_BASE_PARAMS,
        "X-Bogus": sign_params["X-Bogus"],
        "a_bogus": sign_params["a_bogus"],
        "msToken": sign_params["msToken"],
    }
    resp = _make_request(real_cookie, full_params)

    # 3. 验证服务端接受签名
    assert resp.status_code == 200, f"HTTP {resp.status_code} - 签名可能被拒绝"
    data = resp.json()
    assert data.get("status_code") == 0, f"签名验证失败: status_code={data.get('status_code')}"

    # 4. 验证返回有效数据（aweme_detail 可能因风控缺失，签名被接受即视为通过）
    aweme_detail = data.get("aweme_detail")
    if aweme_detail is not None:
        assert aweme_detail.get("aweme_id") == _TEST_AWEME_ID
