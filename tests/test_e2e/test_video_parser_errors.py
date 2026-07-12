"""场景：VideoParser 异常响应处理端到端测试。

验证 VideoParser.parse_video 在异常响应场景下的行为：
    - 不存在的 aweme_id → 业务异常（VideoNotFoundError）或风控异常
    - 空 Cookie 调用 → 风控异常或空响应异常

HTTP 层风控（461/412/429/验证 HTML/网络异常）由 HttpClient 统一抛出；
VideoParser 仅处理 HTTP 200 + ``status_code != 0`` 业务错误与 JSON 字段提取。

依赖说明：
    - ``test_parse_nonexistent_aweme_id`` 需要真实 Cookie（.test_cookie.txt），
      未配置时由 real_cookie fixture 自动 skip。
    - ``test_parse_no_cookie_raises_error`` 不依赖 real_cookie，但通过
      pytestmark 标记为 integration 保持一致性（CI 默认跳过）。
"""

from __future__ import annotations

import sqlite3

import pytest

from app.models import Cookie
from app.repositories import CookieRepository
from crawlers.exceptions import (
    CookieInvalidError,
    NetworkError,
    RateLimitedError,
    VerifyRequiredError,
    VideoNotFoundError,
)
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.video_parser import VideoParser

# 标记所有端到端测试为 integration（CI 默认跳过）
pytestmark = pytest.mark.integration


async def test_parse_nonexistent_aweme_id(
    real_cookie: str,
    clean_db: sqlite3.Connection,
) -> None:
    """不存在的 aweme_id 应抛出业务异常或风控异常。

    aweme_id="0" 在抖音不存在，预期返回 status_code != 0 业务错误，
    VideoParser 将其转换为 VideoNotFoundError。
    若真实 Cookie 在请求过程中被风控，则可能抛出 CookieInvalidError /
    RateLimitedError / VerifyRequiredError / NetworkError。
    """
    # 1. 组装依赖（CookieRepository 注入一个有效 Cookie）
    cookie_repo = CookieRepository(clean_db)
    cookie_repo.add(
        Cookie(
            id=None,
            content=real_cookie,
            label="e2e-test",
            status="valid",
            last_used=None,
            last_check=None,
            fail_count=0,
            created_at="",
        )
    )
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 调用 parse_video（aweme_id="0" 不存在）并验证抛出异常
    try:
        with pytest.raises(
            (
                VideoNotFoundError,
                CookieInvalidError,
                RateLimitedError,
                VerifyRequiredError,
                NetworkError,
            )
        ):
            await video_parser.parse_video("0", real_cookie)
    finally:
        await http_client.close()


async def test_parse_no_cookie_raises_error(
    clean_db: sqlite3.Connection,
) -> None:
    """空 Cookie 调用 parse_video 应抛出风控异常或空响应异常。

    显式传入空字符串 Cookie，HttpClient 会以空 Cookie 发起请求，
    预期触发抖音风控（461/412）或安全验证页面。
    不依赖 real_cookie fixture，但通过 pytestmark 标记为 integration 保持一致性。
    """
    # 1. 组装依赖（CookieRepository 不注入任何 Cookie）
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    video_parser = VideoParser(http_client, signer)

    # 2. 调用 parse_video（空 Cookie）并验证抛出异常
    try:
        with pytest.raises(
            (
                CookieInvalidError,
                RateLimitedError,
                VerifyRequiredError,
                NetworkError,
                VideoNotFoundError,
            )
        ):
            await video_parser.parse_video("7646700367584954368", "")
    finally:
        await http_client.close()
