"""HTTP 客户端模块。

封装 ``httpx.AsyncClient`` 单例，统一注入签名、Cookie、Headers，
提供异步 GET 请求入口与 Cookie 池管理（轮询取用 / 失败上报 / 全池失效检测）。

接口签名与 ``docs/structure/05-接口设计文档.md`` 第 3.5 节保持一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.logger import get_logger
from app.models import Cookie, now_iso
from crawlers.exceptions import CookieInvalidError
from crawlers.signer import DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from app.repositories import CookieRepository
    from crawlers.signer import Signer

logger = get_logger(__name__)

# === 类型别名 ===

CookieStatus = Literal["valid", "invalid", "untested"]

# === 模块级常量 ===

# 默认请求头（与签名算法使用的 UA 保持一致，避免 UA 不匹配导致签名失效）
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 风控响应 HTTP 状态码集合（461/412 统一视为 Cookie 失效/风控）
RISK_STATUS_CODES: frozenset[int] = frozenset({461, 412})

# 滑动验证 HTML 特征字符串（任一命中即判定为验证页面）
VERIFY_HTML_MARKERS: tuple[str, ...] = (
    "captcha_verify",
    "verify_type",
    "verifydouyin",
    "slide_verify",
)

# Cookie 连续失败上限：达到此值后置 status='invalid'
MAX_FAIL_COUNT: int = 3


@dataclass(frozen=True)
class CookieRecord:
    """Cookie 池中一条记录的内存表示。

    与 ``cookies`` 表一行对应，用于在爬虫层与数据层之间传递 Cookie 状态。
    使用 frozen dataclass 保证跨层传递不可变。
    """

    id: int
    content: str
    label: str | None
    status: CookieStatus
    last_used: str | None
    last_check: str | None
    fail_count: int
    created_at: str


def _cookie_to_record(cookie: Cookie) -> CookieRecord:
    """将数据层 Cookie dataclass 转换为爬虫层 CookieRecord。

    参数:
        cookie: ``app.models.Cookie`` 实例（来自 CookieRepository）。

    返回:
        CookieRecord 实例。

    异常:
        ValueError: cookie.id 为 None（未持久化的 Cookie 不能入池）。
    """
    if cookie.id is None:
        raise ValueError("Cookie 未持久化（id=None），不能转换为 CookieRecord")
    return CookieRecord(
        id=cookie.id,
        content=cookie.content,
        label=cookie.label,
        status=cookie.status,  # type: ignore[arg-type]
        last_used=cookie.last_used,
        last_check=cookie.last_check,
        fail_count=cookie.fail_count,
        created_at=cookie.created_at,
    )


class HttpClient:
    """HTTP 客户端。

    封装 ``httpx.AsyncClient``，提供统一请求入口与 Cookie 池管理。
    通过依赖注入接收 CookieRepository 以操作 Cookie 池。

    Cookie 池策略遵循设计文档 4.3 节：
        - 取用：``status='valid'`` 中最久未用优先（由 CookieRepository.get_valid 实现）
        - 失败上报：``fail_count += 1``，连续 ``MAX_FAIL_COUNT`` 次置 invalid
        - 成功上报：重置 ``fail_count = 0``，更新 ``last_used``
        - 全池失效：``get_cookie_from_pool`` 抛 ``CookieInvalidError``

    风控响应处理见 ``_handle_response``。
    """

    def __init__(
        self,
        cookie_repository: CookieRepository,
        signer: Signer,
        timeout_connect: float = 10.0,
        timeout_read: float = 30.0,
    ) -> None:
        """初始化 HTTP 客户端。

        参数:
            cookie_repository: Cookie 池 Repository（v0.0.1 提供）。
            signer: 签名算法入口（v0.0.2 提供）。
            timeout_connect: 连接超时（秒），默认 10.0。
            timeout_read: 读取超时（秒），默认 30.0。
        """
        # 延迟导入 httpx，避免模块导入期触发网络栈初始化
        import httpx

        self._cookie_repository = cookie_repository
        self._signer = signer
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(
                connect=timeout_connect,
                read=timeout_read,
                write=10.0,
                pool=5.0,
            ),
            follow_redirects=False,
            headers=dict(DEFAULT_HEADERS),
        )

    async def close(self) -> None:
        """关闭内部 ``httpx.AsyncClient``，释放连接池。

        调用时机：应用退出时（AsyncWorker.stop）。
        """
        await self._client.aclose()

    # === Cookie 池管理 ===

    def get_cookie_from_pool(self) -> CookieRecord:
        """从 Cookie 池中按"最久未用优先"策略取一条 valid Cookie。

        策略:
            - 仅取 ``status='valid'`` 的记录
            - 按 ``last_used`` 升序，取最早使用的一条（由 CookieRepository.get_valid 实现）
            - 取到后立即更新 ``last_used`` 为当前时间

        返回:
            CookieRecord 实例。

        异常:
            CookieInvalidError: 池中无可用 Cookie（全部 invalid 或池空）。
        """
        cookie = self._cookie_repository.get_valid()
        if cookie is None:
            raise CookieInvalidError("Cookie 池无可用 Cookie")
        # 更新 last_used，标记为刚刚使用
        self._cookie_repository.update_last_used(cookie.id, now_iso())
        logger.debug("从 Cookie 池取用 Cookie id=%s label=%s", cookie.id, cookie.label)
        return _cookie_to_record(cookie)

    def report_cookie_fail(self, cookie_id: int) -> None:
        """上报某条 Cookie 请求失败。

        策略:
            - 该 Cookie ``fail_count += 1``
            - 若 ``fail_count >= MAX_FAIL_COUNT``，置 ``status='invalid'``

        参数:
            cookie_id: 失败的 Cookie 记录 ID。
        """
        cookie = self._cookie_repository.get_by_id(cookie_id)
        if cookie is None:
            logger.warning("上报 Cookie 失败：id=%s 不存在", cookie_id)
            return
        new_fail_count = cookie.fail_count + 1
        self._cookie_repository.update_fail_count(cookie_id, new_fail_count)
        if new_fail_count >= MAX_FAIL_COUNT:
            self._cookie_repository.update_status(cookie_id, "invalid")
            logger.warning(
                "Cookie id=%s 连续失败 %d 次，标记为 invalid",
                cookie_id,
                new_fail_count,
            )
        else:
            logger.debug(
                "Cookie id=%s 失败计数 %d/%d",
                cookie_id,
                new_fail_count,
                MAX_FAIL_COUNT,
            )

    def report_cookie_success(self, cookie_id: int) -> None:
        """上报某条 Cookie 请求成功，重置 fail_count。

        参数:
            cookie_id: 成功的 Cookie 记录 ID。
        """
        self._cookie_repository.update_fail_count(cookie_id, 0)
        self._cookie_repository.update_last_used(cookie_id, now_iso())
        logger.debug("Cookie id=%s 请求成功，fail_count 已重置", cookie_id)

    def check_all_cookies_invalid(self) -> bool:
        """检查池里是否所有 Cookie 都失效（无 valid 记录）。

        返回:
            池中无 valid Cookie 返回 True，否则 False。
        """
        cookie = self._cookie_repository.get_valid()
        return cookie is None
