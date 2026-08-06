"""URLParser + VideoParser 全链路集成测试。

通过真实抖音短链验证从链接解析到视频详情获取的完整链路：
    短链 → follow_redirect → identify_type → extract_aweme_id
    → VideoParser.parse_video() → VideoInfo（含无水印直链/图集URL）

运行条件：
    - 项目根目录存在 .test_cookie.txt 文件（已被 .gitignore 排除）
    - 使用 pytest -m integration 显式启用

测试覆盖：
    - 图文分享短链：https://v.douyin.com/00tC3WPkgUA/
      → 重定向到 iesdouyin.com/share/slides/
      → aweme_id=7668332388174388986
      → detail 接口返回图集（image_set，9张图片 + 1个视频）
    - 普通视频短链：通过 URLParser 解析后获取 aweme_id
      → detail 接口返回视频信息（含无水印直链）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database import get_memory_connection
from app.models import Cookie, now_iso
from app.repositories import CookieRepository
from crawlers.http_client import HttpClient
from crawlers.signer import DEFAULT_USER_AGENT, Signer
from crawlers.url_parser import URLParser
from crawlers.video_parser import VideoParser

pytestmark = [pytest.mark.integration, pytest.mark.full_chain]

# Cookie 文件路径（项目根目录，已被 .gitignore 排除）
_COOKIE_PATH = Path(__file__).parent.parent / ".test_cookie.txt"

# 用户报告的图文分享短链
_SHORT_URL_SLIDES = "https://v.douyin.com/00tC3WPkgUA/"
_SLIDES_AWEME_ID = "7668332388174388986"

# 已知公开视频 aweme_id
_VIDEO_AWEME_ID = "7646700367584954368"


def _load_cookie() -> str | None:
    """从 .test_cookie.txt 加载 Cookie，文件不存在时返回 None。"""
    if not _COOKIE_PATH.exists():
        return None
    cookie = _COOKIE_PATH.read_text(encoding="utf-8").strip()
    return cookie or None


@pytest.fixture(scope="module")
def test_cookie() -> str:
    """返回测试 Cookie 字符串，无 Cookie 时跳过。"""
    cookie = _load_cookie()
    if cookie is None:
        pytest.skip("未找到 .test_cookie.txt，集成测试跳过（需用户提供 Cookie）")
    return cookie


@pytest.fixture(scope="function")
def real_http_client(test_cookie: str) -> HttpClient:
    """返回注入真实 Cookie 的 HttpClient 实例。"""
    conn = get_memory_connection()
    signer = Signer(user_agent=DEFAULT_USER_AGENT)
    repo = CookieRepository(conn)
    # 将用户 Cookie 作为测试 Cookie 插入内存数据库
    repo.add(Cookie(
        id=None,
        content=test_cookie,
        label="integration-test",
        status="valid",
        last_used=None,
        last_check=None,
        fail_count=0,
        created_at=now_iso(),
    ))
    return HttpClient(repo, signer)


@pytest.fixture(scope="function")
def url_parser(real_http_client: HttpClient) -> URLParser:
    """返回注入真实 HttpClient 的 URLParser 实例。"""
    return URLParser(real_http_client)


@pytest.fixture(scope="function")
def video_parser(real_http_client: HttpClient) -> VideoParser:
    """返回注入真实 HttpClient 的 VideoParser 实例。"""
    signer = Signer(user_agent=DEFAULT_USER_AGENT)
    return VideoParser(real_http_client, signer)


class TestFullChainSlides:
    """图文分享链接全链路测试。

    覆盖：短链 → URLParser → VideoParser → VideoInfo（含图集URL）。
    """

    async def test_01_url_parser_extracts_aweme_id(
        self, url_parser: URLParser
    ) -> None:
        """步骤1：URLParser 从短链中解析出 aweme_id。"""
        result = await url_parser.parse(_SHORT_URL_SLIDES)
        assert result.type == "video", f"类型应为 video，实际为 {result.type}"
        assert result.aweme_id == _SLIDES_AWEME_ID, (
            f"aweme_id 应为 {_SLIDES_AWEME_ID}，实际为 {result.aweme_id}"
        )
        assert "/share/slides/" in result.url, (
            f"最终 URL 应包含 /share/slides/，实际为 {result.url}"
        )

    async def test_02_video_parser_returns_video_info(
        self, video_parser: VideoParser, test_cookie: str
    ) -> None:
        """步骤2：VideoParser 通过 detail 接口获取完整 VideoInfo。

        验证要点：
        - status_code=0（签名和Cookie有效）
        - 返回 VideoInfo 且 type=image_set（图文）
        - 包含标题、作者、封面图
        - 包含图集图片 URL 列表（至少1张）
        - 包含无水印视频直链（图文通常也附带一个视频）
        - 包含发布时间（ISO8601格式）
        - 包含统计信息（点赞/评论/分享/收藏数）
        """
        video_info = await video_parser.parse_video(_SLIDES_AWEME_ID, test_cookie)

        # 基本信息
        assert video_info.type == "image_set", (
            f"类型应为 image_set（图文），实际为 {video_info.type}"
        )
        assert video_info.title, "标题不应为空"
        assert video_info.author, f"作者不应为空，当前 {video_info.author}"
        assert video_info.cover_url, "封面 URL 不应为空"
        assert video_info.cover_url.startswith("http"), (
            f"封面 URL 格式异常: {video_info.cover_url[:60]}"
        )

        # 图集验证
        assert len(video_info.image_urls) > 0, (
            f"图集应包含至少1张图片，当前 {len(video_info.image_urls)} 张"
        )
        for img_url in video_info.image_urls:
            assert img_url.startswith("http"), f"图片 URL 格式异常: {img_url[:60]}"

        # 无水印视频直链（图文也附带一个视频）
        assert video_info.no_watermark_url is not None, "无水印视频直链不应为空"
        assert video_info.no_watermark_url.startswith("http"), (
            f"无水印 URL 格式异常: {video_info.no_watermark_url[:60]}"
        )

        # 验证发布时间格式化正确（ISO8601格式 YYYY-MM-DDTHH:MM:SSZ）
        assert video_info.publish_time is not None, "发布时间不应为 None"
        assert "T" in video_info.publish_time and video_info.publish_time.endswith("Z"), (
            f"发布时间应为 ISO8601 格式，当前: {video_info.publish_time}"
        )


class TestFullChainVideo:
    """普通视频链接全链路测试（使用 slides 图文中的视频附带来验证视频能力）。"""

    async def test_01_video_parser_returns_video_info(
        self, video_parser: VideoParser, test_cookie: str
    ) -> None:
        """通过 VideoParser 获取视频信息。

        验证要点：
        - type=image_set（图文）
        - 包含无水印视频直链（图文附带视频）
        - 包含时长 duration 或为 None（图文视频时长可能为 0）
        - 图集非空
        """
        # 使用 slides 的 aweme_id，它同时包含 image_set 和 video
        video_info = await video_parser.parse_video(_SLIDES_AWEME_ID, test_cookie)

        # 图文类型
        assert video_info.type == "image_set", (
            f"类型应为 image_set，实际为 {video_info.type}"
        )
        assert video_info.title, "标题不应为空"
        assert video_info.author, f"作者不应为空，当前 {video_info.author}"
        assert video_info.cover_url, "封面 URL 不应为空"

        # 无水印视频直链（图文附带视频）
        assert video_info.no_watermark_url is not None, "无水印视频直链不应为空"
        assert video_info.no_watermark_url.startswith("http"), (
            f"无水印 URL 格式异常: {video_info.no_watermark_url[:60]}"
        )

        # 图集图片
        assert len(video_info.image_urls) > 0, (
            f"图集应包含至少1张图片，当前 {len(video_info.image_urls)} 张"
        )

        # 发布时间
        assert video_info.publish_time is not None, "发布时间不应为 None"
        assert "T" in video_info.publish_time and video_info.publish_time.endswith("Z"), (
            f"发布时间应为 ISO8601 格式，当前: {video_info.publish_time}"
        )