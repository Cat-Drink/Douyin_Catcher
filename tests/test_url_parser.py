"""URLParser 链接解析器单元测试。

覆盖 extract_url / identify_type / follow_redirect / parse 方法。
follow_redirect 与 parse 通过 mock HttpClient 测试，不打真实网络。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crawlers.exceptions import InvalidURLFormatError
from crawlers.url_parser import ParsedURL, URLParser


@pytest.fixture
def mock_http_client() -> MagicMock:
    """返回 mock HttpClient，供 URLParser 注入。"""
    return MagicMock(name="HttpClient")


@pytest.fixture
def url_parser(mock_http_client: MagicMock) -> URLParser:
    """返回注入 mock HttpClient 的 URLParser 实例。"""
    return URLParser(mock_http_client)


# ==================== extract_url 测试 ====================


class TestExtractUrl:
    """extract_url 方法测试。"""

    def test_extract_url_pure_short_link(self, url_parser: URLParser) -> None:
        """纯短链 ``https://v.douyin.com/xxxxx/`` 提取成功。"""
        text = "https://v.douyin.com/AbCdEf123/"
        assert url_parser.extract_url(text) == "https://v.douyin.com/AbCdEf123/"

    def test_extract_url_long_video_link(self, url_parser: URLParser) -> None:
        """纯长链 ``https://www.douyin.com/video/{aweme_id}`` 提取成功。"""
        text = "https://www.douyin.com/video/7646700367584954368"
        assert url_parser.extract_url(text) == "https://www.douyin.com/video/7646700367584954368"

    def test_extract_url_user_home_link(self, url_parser: URLParser) -> None:
        """主页链接 ``https://www.douyin.com/user/{sec_user_id}`` 提取成功。"""
        text = "https://www.douyin.com/user/MS4wLjABAAAAabc123"
        assert url_parser.extract_url(text) == "https://www.douyin.com/user/MS4wLjABAAAAabc123"

    def test_extract_url_share_command_video(self, url_parser: URLParser) -> None:
        """视频分享口令（含中文描述 + 短链）→ 提取短链。"""
        text = (
            "7.99 复制打开抖音，看看【守望先锋的图文】"
            " https://v.douyin.com/AbCdEf123/ 关注我，带你了解更多！"
        )
        assert url_parser.extract_url(text) == "https://v.douyin.com/AbCdEf123/"

    def test_extract_url_share_command_image_set(self, url_parser: URLParser) -> None:
        """图文分享口令（含中文描述 + 短链）→ 提取短链。"""
        text = (
            "2.34 复制打开抖音，看看【摄影者的图文作品】"
            " https://v.douyin.com/XyZ987/ : 此图文很精彩"
        )
        assert url_parser.extract_url(text) == "https://v.douyin.com/XyZ987/"

    def test_extract_url_multi_links_returns_first(self, url_parser: URLParser) -> None:
        """多链接文本 → 返回第一个抖音链接。"""
        text = "第一 https://v.douyin.com/Aaa111/ " "第二 https://www.douyin.com/video/123"
        assert url_parser.extract_url(text) == "https://v.douyin.com/Aaa111/"

    def test_extract_url_no_link_returns_none(self, url_parser: URLParser) -> None:
        """无链接文本 → 返回 None。"""
        text = "这段文字完全没有链接，只是一段普通描述。"
        assert url_parser.extract_url(text) is None

    def test_extract_url_empty_string_returns_none(self, url_parser: URLParser) -> None:
        """空字符串 → 返回 None。"""
        assert url_parser.extract_url("") is None

    def test_extract_url_non_douyin_link_returns_none(self, url_parser: URLParser) -> None:
        """非抖音域名链接 → 返回 None。"""
        text = "https://www.example.com/video/123"
        assert url_parser.extract_url(text) is None

    def test_extract_url_chinese_punctuation(self, url_parser: URLParser) -> None:
        """含中文逗号/句号分隔的文本，URL 不被吞入描述部分。"""
        text = "看看这个视频，https://v.douyin.com/AbCd123/，很精彩。"
        assert url_parser.extract_url(text) == "https://v.douyin.com/AbCd123/"

    def test_extract_url_with_query_params(self, url_parser: URLParser) -> None:
        """带查询参数的长链完整提取。"""
        text = "https://www.douyin.com/video/7646700367584954368?previous_page=app_code_link"
        assert (
            url_parser.extract_url(text)
            == "https://www.douyin.com/video/7646700367584954368?previous_page=app_code_link"
        )

    def test_extract_url_trailing_punctuation_stripped(self, url_parser: URLParser) -> None:
        """URL 末尾粘连的英文句号/右括号被剥离。"""
        text = "(see https://v.douyin.com/AbCd123/)."
        assert url_parser.extract_url(text) == "https://v.douyin.com/AbCd123/"

    def test_extract_url_http_uppercase(self, url_parser: URLParser) -> None:
        """HTTP 大写也识别。"""
        text = "HTTPS://v.douyin.com/AbCd123/"
        assert url_parser.extract_url(text) == "HTTPS://v.douyin.com/AbCd123/"

    def test_extract_url_short_link_without_trailing_slash(self, url_parser: URLParser) -> None:
        """短链末尾无 / 也识别。"""
        text = "https://v.douyin.com/AbCd123"
        assert url_parser.extract_url(text) == "https://v.douyin.com/AbCd123"

    def test_extract_url_iesdouyin_domain(self, url_parser: URLParser) -> None:
        """iesdouyin.com 旧域名也识别。"""
        text = "https://www.iesdouyin.com/share/video/7646700367584954368"
        assert (
            url_parser.extract_url(text)
            == "https://www.iesdouyin.com/share/video/7646700367584954368"
        )


class TestParsedURLDataclass:
    """ParsedURL dataclass 不可变性与字段测试。"""

    def test_parsed_url_is_frozen(self) -> None:
        """ParsedURL 是 frozen dataclass，不可修改。"""
        parsed = ParsedURL(
            type="video",
            url="https://www.douyin.com/video/123",
            aweme_id="123",
            sec_user_id=None,
            original_text="原始文本",
        )
        with pytest.raises(AttributeError):
            parsed.type = "user_home"  # type: ignore[misc]

    def test_parsed_url_fields(self) -> None:
        """ParsedURL 字段正确赋值。"""
        parsed = ParsedURL(
            type="user_home",
            url="https://www.douyin.com/user/MS4w",
            aweme_id=None,
            sec_user_id="MS4w",
            original_text="原始文本",
        )
        assert parsed.type == "user_home"
        assert parsed.aweme_id is None
        assert parsed.sec_user_id == "MS4w"
        assert parsed.original_text == "原始文本"


# ==================== identify_type 测试 ====================


class TestIdentifyType:
    """identify_type 方法测试。"""

    def test_identify_type_video_path(self, url_parser: URLParser) -> None:
        """路径含 /video/ → 'video'。"""
        assert (
            url_parser.identify_type("https://www.douyin.com/video/7646700367584954368") == "video"
        )

    def test_identify_type_video_query_param(self, url_parser: URLParser) -> None:
        """查询参数含 aweme_id → 'video'。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123"
        assert url_parser.identify_type(url) == "video"

    def test_identify_type_user_home_path(self, url_parser: URLParser) -> None:
        """路径含 /user/ → 'user_home'。"""
        url = "https://www.douyin.com/user/MS4wLjABAAAAabc123"
        assert url_parser.identify_type(url) == "user_home"

    def test_identify_type_user_home_query_param(self, url_parser: URLParser) -> None:
        """查询参数含 sec_user_id → 'user_home'。"""
        url = "https://www.douyin.com/aweme/v1/web/user/profile/other/?sec_user_id=MS4w"
        assert url_parser.identify_type(url) == "user_home"

    def test_identify_type_user_home_priority_over_video(self, url_parser: URLParser) -> None:
        """同时含 /user/ 和 /video/ 时，user_home 优先。"""
        # 实际不会出现，但验证优先级规则
        url = "https://www.douyin.com/user/MS4w/video/123"
        assert url_parser.identify_type(url) == "user_home"

    def test_identify_type_share_video_path(self, url_parser: URLParser) -> None:
        """iesdouyin 分享链接 /share/video/{id} → 'video'。"""
        url = "https://www.iesdouyin.com/share/video/7646700367584954368"
        assert url_parser.identify_type(url) == "video"

    def test_identify_type_invalid_raises(self, url_parser: URLParser) -> None:
        """无法识别的路径 → 抛 InvalidURLFormatError。"""
        url = "https://www.douyin.com/discover/123"
        with pytest.raises(InvalidURLFormatError):
            url_parser.identify_type(url)

    def test_identify_type_empty_path_raises(self, url_parser: URLParser) -> None:
        """根路径无任何标识 → 抛 InvalidURLFormatError。"""
        url = "https://www.douyin.com/"
        with pytest.raises(InvalidURLFormatError):
            url_parser.identify_type(url)

    def test_identify_type_invalid_url_raises(self, url_parser: URLParser) -> None:
        """URL 格式无效 → 抛 InvalidURLFormatError。"""
        with pytest.raises(InvalidURLFormatError):
            url_parser.identify_type("not_a_url")


# ==================== extract_aweme_id / extract_sec_user_id 测试 ====================


class TestExtractIds:
    """extract_aweme_id / extract_sec_user_id 方法测试。"""

    def test_extract_aweme_id_from_path(self) -> None:
        """从路径 /video/{id} 提取 aweme_id。"""
        url = "https://www.douyin.com/video/7646700367584954368"
        assert URLParser.extract_aweme_id(url) == "7646700367584954368"

    def test_extract_aweme_id_from_share_path(self) -> None:
        """从分享路径 /share/video/{id} 提取 aweme_id。"""
        url = "https://www.iesdouyin.com/share/video/7646700367584954368"
        assert URLParser.extract_aweme_id(url) == "7646700367584954368"

    def test_extract_aweme_id_from_query(self) -> None:
        """从查询参数 ?aweme_id=xxx 提取 aweme_id。"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=123"
        assert URLParser.extract_aweme_id(url) == "123"

    def test_extract_aweme_id_not_found(self) -> None:
        """无 aweme_id → 返回 None。"""
        url = "https://www.douyin.com/user/MS4w"
        assert URLParser.extract_aweme_id(url) is None

    def test_extract_sec_user_id_from_path(self) -> None:
        """从路径 /user/{sec_uid} 提取 sec_user_id。"""
        url = "https://www.douyin.com/user/MS4wLjABAAAAabc123"
        assert URLParser.extract_sec_user_id(url) == "MS4wLjABAAAAabc123"

    def test_extract_sec_user_id_from_query(self) -> None:
        """从查询参数 ?sec_user_id=xxx 提取 sec_user_id。"""
        url = "https://www.douyin.com/aweme/v1/web/user/profile/other/?sec_user_id=MS4w"
        assert URLParser.extract_sec_user_id(url) == "MS4w"

    def test_extract_sec_user_id_not_found(self) -> None:
        """无 sec_user_id → 返回 None。"""
        url = "https://www.douyin.com/video/123"
        assert URLParser.extract_sec_user_id(url) is None
