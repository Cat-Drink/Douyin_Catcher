"""用户主页抓取器模块。

根据 ``sec_user_id`` 分页拉取抖音 ``aweme/v1/web/aweme/post`` 接口，
按类型/数量/时间段过滤后异步产出 ``PostItem`` 流。

接口契约见 ``docs/structure/05-接口设计文档.md`` 第 3.4 节；
实现规范见 ``docs/plans/v0.0.4-视频解析与主页抓取.md`` 第 4 节。

设计要点:
    - 通过依赖注入接收 HttpClient 与 Signer，不持有网络连接
    - HTTP 层风控（461/412/429/验证 HTML/网络异常）已由 HttpClient 统一处理
    - 本模块仅处理 HTTP 200 + ``status_code != 0`` 业务错误与分页/过滤逻辑
    - 字段命名沿用计划文档 4.2.1 节（max_count / start_date / end_date），
      与接口文档 3.4 节的 count_limit / date_from / date_to 等价
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from crawlers.http_client import HttpClient
    from crawlers.signer import Signer


# === 类型别名 ===

# 主页抓取类型过滤（与计划文档 11.2 节一致）
HomeFilterType = Literal["all", "video", "image_set", "long_video"]


# === 数据结构 ===


@dataclass(frozen=True)
class HomeFilters:
    """主页抓取过滤条件。

    字段命名沿用 v0.0.4 计划文档 4.2.1 节，与接口文档 3.4 节的
    ``count_limit`` / ``date_from`` / ``date_to`` 等价：
        - ``max_count`` ≡ ``count_limit``：数量上限，``0`` 表示不限
        - ``start_date`` ≡ ``date_from``：起始日期 ``YYYY-MM-DD``（含），``None`` 不限
        - ``end_date`` ≡ ``date_to``：结束日期 ``YYYY-MM-DD``（含当日 23:59:59），``None`` 不限
    """

    type_filter: HomeFilterType = "all"
    max_count: int = 0
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True)
class PostItem:
    """主页作品列表项（轻量信息，供 UI 勾选）。

    与 VideoInfo 不同，PostItem 不含无水印直链——直链在用户勾选后
    由 VideoParser 二次调用 detail 接口获取（见计划文档 4.2.2 节）。
    """

    aweme_id: str
    title: str
    author: str
    author_sec_id: str
    cover_url: str
    type: str
    create_time: str
    duration: str | None
    image_count: int | None


# === UserHomeCrawler 类（Step 7-8 补充实现） ===


class UserHomeCrawler:
    """用户主页抓取器。

    调用 aweme/v1/web/aweme/post 接口分页拉取，使用 max_cursor 翻页。

    异常处理:
        HTTP 层风控异常（CookieInvalidError / RateLimitedError /
        VerifyRequiredError / NetworkError）由 HttpClient 直接抛出；
        本类仅处理:
            - ``status_code != 0`` 业务错误 → UserNotFoundError
            - ``aweme_list`` 字段缺失 → 视为空列表，正常结束迭代
    """

    def __init__(self, http_client: HttpClient, signer: Signer) -> None:
        """初始化主页抓取器。

        参数:
            http_client: HttpClient 实例（提供签名 + Cookie 注入的请求能力）。
            signer: Signer 实例（保留注入以便未来扩展）。
        """
        self._http_client = http_client
        self._signer = signer
