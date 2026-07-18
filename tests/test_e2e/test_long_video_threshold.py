"""场景：长视频阈值边界类型识别端到端测试（v0.1.3 / v0.1.8 plan 3）。

验证长视频阈值（30 分钟）的类型识别：
    长视频 aweme_id -> VideoParser.parse_video -> type == "long_video"

覆盖 v0.1.3 用户反馈 #12：长视频阈值从文件大小改为时长（>=30 分钟为 long_video）。

注：30 分钟整 / 29 分钟的精确边界验证在单元测试 test_video_parser.py::TestDetectVideoType
中已完整覆盖（test_detect_type_duration_exactly_threshold / _below_threshold）。
本 e2e 场景验证真实长视频被识别为 long_video 类型，不执行下载（长视频文件较大）。

需要真实 Cookie（.test_cookie.txt）与真实长视频 aweme_id（.test_long_video_aweme_id.txt）。
"""

from __future__ import annotations

import sqlite3

import pytest

from app.repositories import CookieRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.video_parser import VideoParser
from downloader.constants import LONG_VIDEO_DURATION_THRESHOLD

# 标记所有端到端测试为 integration（CI 默认跳过）
pytestmark = pytest.mark.integration


def _parse_duration_to_seconds(duration: str) -> int:
    """将 "HH:MM:SS" 或 "MM:SS" 时长字符串解析为总秒数。"""
    parts = duration.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    raise ValueError(f"无法解析时长字符串: {duration}")


async def test_long_video_threshold_boundary(
    real_cookie: str,
    real_long_video_aweme_id: str,
    clean_db: sqlite3.Connection,
) -> None:
    """验证长视频 aweme_id 被识别为 long_video 类型且时长 >= 30 分钟阈值。

    步骤：
        1. VideoParser.parse_video 解析长视频
        2. 验证 type == "long_video"
        3. 验证 duration 字符串解析后 >= LONG_VIDEO_DURATION_THRESHOLD（1800 秒）
    """
    # 1. 组装依赖
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    video_parser = VideoParser(http_client, signer)

    try:
        # 2. 构造分享链接并解析
        share_url = f"https://www.douyin.com/video/{real_long_video_aweme_id}"
        parsed = await url_parser.parse(share_url)
        assert parsed.aweme_id == real_long_video_aweme_id

        # 3. 解析视频信息，验证类型为 long_video
        video_info = await video_parser.parse_video(real_long_video_aweme_id, real_cookie)
        assert (
            video_info.type == "long_video"
        ), f"长视频应识别为 long_video，实际为 {video_info.type}"

        # 4. 验证时长 >= 30 分钟阈值（1800 秒）
        assert video_info.duration is not None, "长视频 duration 不应为 None"
        duration_seconds = _parse_duration_to_seconds(video_info.duration)
        assert duration_seconds >= LONG_VIDEO_DURATION_THRESHOLD, (
            f"长视频时长 {duration_seconds}s 应 >= 阈值 "
            f"{LONG_VIDEO_DURATION_THRESHOLD}s（30 分钟）"
        )
    finally:
        await http_client.close()
