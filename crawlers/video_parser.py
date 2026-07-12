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

    # === 私有辅助方法 ===

    @staticmethod
    def _detect_video_type(detail: dict) -> VideoType:
        """根据响应数据判断作品类型。

        判断顺序（先命中先返回，见计划文档 3.5 节）:
            1. ``images`` 字段非空（列表长度 > 0） → ``'image_set'``
            2. ``video.duration`` > 60000 毫秒（> 60 秒） → ``'long_video'``
            3. 其他情况 → ``'video'``

        参数:
            detail: ``aweme_detail`` 节点。

        返回:
            ``'video'`` / ``'image_set'`` / ``'long_video'``。
        """
        images = detail.get("images")
        if isinstance(images, list) and len(images) > 0:
            return "image_set"
        duration = detail.get("video", {}).get("duration", 0) or 0
        if duration > 60000:
            return "long_video"
        return "video"

    @staticmethod
    def _format_duration(ms: int) -> str:
        """毫秒转展示文本。

        规则:
            - < 60 秒 → ``'Xs'``（如 ``'15s'``）
            - >= 60 秒 → ``'MM:SS'``（如 ``'12:30'``），小时以上仍按 MM:SS 展示
              （如 1 小时 30 分 15 秒 → ``'90:15'``）

        参数:
            ms: 视频时长（毫秒）。

        返回:
            展示文本。
        """
        total_seconds = ms // 1000
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _extract_tags(detail: dict) -> list[str]:
        """从 ``text_extra`` 提取标签名列表。

        参数:
            detail: ``aweme_detail`` 节点。

        返回:
            标签名列表（无标签时为空列表）。
        """
        text_extra = detail.get("text_extra")
        if not isinstance(text_extra, list):
            return []
        tags: list[str] = []
        for item in text_extra:
            if not isinstance(item, dict):
                continue
            name = item.get("hashtag_name")
            if isinstance(name, str) and name:
                tags.append(name)
        return tags

    @staticmethod
    def _extract_no_watermark_url(detail: dict) -> str | None:
        """提取视频无水印直链。

        路径（见计划文档 3.4.1 节）:
            - 主路径: ``video.play_addr.url_list[0]``
            - 回退: 若 URL 含 ``playwm`` 子串，替换为 ``play`` 得无水印直链

        参数:
            detail: ``aweme_detail`` 节点。

        返回:
            无水印直链；列表为空时返回 None。
        """
        url_list = detail.get("video", {}).get("play_addr", {}).get("url_list")
        if not isinstance(url_list, list) or not url_list:
            return None
        url = url_list[0]
        if not isinstance(url, str) or not url:
            return None
        if "playwm" in url:
            url = url.replace("playwm", "play")
        return url

    @staticmethod
    def _extract_image_urls(detail: dict) -> list[str]:
        """提取图集原图直链列表。

        路径（见计划文档 3.4.2 节）: 遍历 ``images`` 数组，每项取 ``url_list[0]``。

        参数:
            detail: ``aweme_detail`` 节点。

        返回:
            图片 URL 列表（无图集时为空列表）。
        """
        images = detail.get("images")
        if not isinstance(images, list):
            return []
        urls: list[str] = []
        for img in images:
            if not isinstance(img, dict):
                continue
            url_list = img.get("url_list")
            if not isinstance(url_list, list) or not url_list:
                continue
            url = url_list[0]
            if isinstance(url, str) and url:
                urls.append(url)
        return urls
