"""链接解析器模块。

从用户粘贴的分享文本中提取抖音链接，识别链接类型，解析出作品 ID 或
用户主页 sec_user_id。短链重定向通过注入的 HttpClient 完成。

接口签名与 ``docs/structure/05-接口设计文档.md`` 第 3.1 节保持一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from crawlers.http_client import HttpClient

# === 类型别名 ===

LinkType = Literal["video", "image_set", "long_video", "user_home"]

# === 模块级常量 ===

# 通用 URL 提取正则：匹配 http(s):// 开头、到空白或中文标点结束的子串
# 中文逗号/句号/顿号/感叹号/问号 作为分隔符，避免吞入分享文本的描述部分
# 注意：英文 ? 与 ! 不作为终止符，因为它们是合法 URL 字符（查询分隔符/sub-delim）
_URL_PATTERN: re.Pattern[str] = re.compile(
    r"https?://[^\s，。、！？,;；)）\]]+",
    re.IGNORECASE,
)

# 抖音合法域名集合（短链 + 长链）
# - v.douyin.com：分享短链
# - www.douyin.com / douyin.com：长链（视频/主页）
# - iesdouyin.com：旧域名兼容
_DOUYIN_DOMAINS: tuple[str, ...] = (
    "v.douyin.com",
    "www.douyin.com",
    "douyin.com",
    "www.iesdouyin.com",
    "iesdouyin.com",
)


@dataclass(frozen=True)
class ParsedURL:
    """URL 解析结果。

    type 为 'video' | 'image_set' | 'long_video' 时，aweme_id 必填、sec_user_id 为 None。
    type 为 'user_home' 时，sec_user_id 必填、aweme_id 为 None。

    注：image_set 与 long_video 的最终判定依赖 VideoParser 调用 detail 接口后的结果，
        URLParser 仅在能从 URL 直接判断时给出预判，否则默认归为 'video'。
    """

    type: LinkType
    url: str
    aweme_id: str | None
    sec_user_id: str | None
    original_text: str


class URLParser:
    """链接解析器。

    纯逻辑组件，不持有网络连接；如需跟随短链重定向，通过注入的 HttpClient 完成。

    解析流程（parse 方法编排）：
        extract_url → follow_redirect（如需）→ identify_type → 构造 ParsedURL
    """

    def __init__(self, http_client: HttpClient) -> None:
        """初始化链接解析器。

        参数:
            http_client: 用于跟随短链重定向的 HttpClient 实例。
        """
        self._http_client = http_client

    def extract_url(self, text: str) -> str | None:
        """从任意文本中提取第一个抖音链接 URL。

        支持识别的输入格式：
            - 抖音短链：``https://v.douyin.com/xxxxx/``
            - 抖音长链（视频）：``https://www.douyin.com/video/{aweme_id}``
            - 抖音长链（主页）：``https://www.douyin.com/user/{sec_user_id}``
            - 分享口令（含中文描述 + 短链）
            - 多链接文本（取第一个）

        参数:
            text: 原始文本。

        返回:
            提取到的 URL 字符串；未找到返回 None。
        """
        if not text:
            return None
        for match in _URL_PATTERN.finditer(text):
            url = match.group(0)
            # 去除末尾可能粘连的标点（如右括号、句号）
            url = url.rstrip(".,;:)]}。，；：）】》")
            if self._is_douyin_url(url):
                return url
        return None

    @staticmethod
    def _is_douyin_url(url: str) -> bool:
        """判断 URL 是否属于抖音合法域名。

        参数:
            url: 待判断的 URL 字符串。

        返回:
            属于抖音域名返回 True，否则 False。
        """
        url_lower = url.lower()
        # 提取 host 部分：https://host/path → host
        host_match = re.match(r"https?://([^/]+)/?", url_lower)
        if not host_match:
            return False
        host = host_match.group(1).split(":")[0]
        return host in _DOUYIN_DOMAINS
