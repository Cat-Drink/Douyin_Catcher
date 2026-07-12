"""视频解析器模块。

根据 ``aweme_id`` 调用抖音 ``aweme/v1/web/aweme/detail`` 接口，
解析出无水印直链与完整元数据，区分 video / image_set / long_video 三种类型。

接口契约见 ``docs/structure/05-接口设计文档.md`` 第 3.3 节；
实现规范见 ``docs/plans/v0.0.4-视频解析与主页抓取.md`` 第 3 节。

设计要点:
    - 通过依赖注入接收 HttpClient 与 Signer，不持有网络连接
    - HTTP 层风控（461/412/429/验证 HTML/网络异常）已由 HttpClient 统一处理
    - 本模块仅处理 HTTP 200 + ``status_code != 0`` 业务错误与 JSON 字段提取
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from crawlers.http_client import HttpClient
    from crawlers.signer import Signer


# === 类型别名 ===

# 抖音作品类型（与计划文档 11.2 节一致，供 UserHomeCrawler 复用）
VideoType = Literal["video", "image_set", "long_video"]


# === 数据结构 ===


@dataclass(frozen=True)
class VideoInfo:
    """视频/图集解析结果。

    类型与字段对应关系:
        - ``type='video'`` 或 ``'long_video'`` 时：
          ``no_watermark_url`` 必填、``image_urls`` 为空列表、``duration`` 非 None
        - ``type='image_set'`` 时：
          ``image_urls`` 必填（至少 1 条）、``no_watermark_url`` 为 None、
          ``duration`` 为 None

    字段来源映射见计划文档 3.2 节字段清单。
    """

    aweme_id: str
    type: VideoType
    title: str
    author: str
    author_sec_id: str
    duration: str | None
    cover_url: str
    no_watermark_url: str | None
    image_urls: list[str]
    publish_time: str | None
    like_count: int
    comment_count: int
    share_count: int
    collect_count: int
    tags: list[str]
    raw_json: dict


# === VideoParser 类（Step 3-4 补充实现） ===


class VideoParser:
    """视频解析器。

    依赖 HttpClient（注入签名与 Cookie）调用抖音 detail 接口，
    从响应中提取无水印直链与元数据。

    异常处理:
        HTTP 层风控异常（CookieInvalidError / RateLimitedError /
        VerifyRequiredError / NetworkError）由 HttpClient 直接抛出；
        本类仅处理:
            - ``status_code != 0`` 业务错误 → VideoNotFoundError
            - JSON 结构不符合预期 → VideoNotFoundError
    """

    def __init__(self, http_client: HttpClient, signer: Signer) -> None:
        """初始化视频解析器。

        参数:
            http_client: HttpClient 实例（提供签名 + Cookie 注入的请求能力）。
            signer: Signer 实例（保留注入以便未来扩展自定义请求参数）。
        """
        self._http_client = http_client
        self._signer = signer
