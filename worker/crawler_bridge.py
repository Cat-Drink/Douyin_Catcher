"""爬虫层桥接器模块。

连接 UI 控制信号 → ``URLParser`` / ``UserHomeCrawler`` / ``CookieTester`` 调用，
连接爬虫层结果 → UI 更新信号；支持 ``cancel_parse`` / ``cancel_home_fetch``
通过 ``asyncio.Task.cancel`` 取消。

严格遵循设计文档 6 节（爬虫组件层）与 v0.0.6 计划文档任务 4。

职责边界：
    - 桥接器只做转发与数据结构转换，不含解析/抓取业务逻辑
    - 业务逻辑在 ``crawlers/`` 的各组件中
    - 取消操作通过持有 ``asyncio.Task`` 引用并调用 ``.cancel()`` 实现

取消机制：
    - ``_parse_task`` / ``_home_fetch_task`` 持有当前任务的 ``asyncio.Task`` 引用
    - 取消时在工作线程的 loop 中调用 ``task.cancel()``
    - 取消时不发射 ``parse_failed`` / ``home_fetch_failed`` 信号（用户主动取消不算失败）
    - 收到新的 ``start_parse`` 时先取消旧任务再启动新任务
"""

from __future__ import annotations

import asyncio
import contextlib

from PySide6.QtCore import QObject

from app.logger import get_logger
from app.repositories import CookieRepository
from crawlers.cookie_tester import CookieTester
from crawlers.exceptions import CookieInvalidError
from crawlers.url_parser import URLParser
from crawlers.user_home_crawler import HomeFilters, PostItem, UserHomeCrawler
from worker.async_worker import AsyncWorker
from worker.signals import ControlSignals, WorkerSignals

logger = get_logger(__name__)


class CrawlerBridge(QObject):
    """爬虫层桥接器：UI 控制信号 ↔ URLParser/UserHomeCrawler/CookieTester + 结果 → UI 信号。

    信号流向：
        UI → ``ControlSignals.start_parse`` → ``on_start_parse`` 槽 →
        ``async_worker.submit`` → ``_do_parse`` → ``url_parser.parse`` →
        ``worker_signals.parse_completed`` / ``parse_failed``

    取消支持：
        - ``cancel_parse`` → 取消 ``_parse_task``
        - ``cancel_home_fetch`` → 取消 ``_home_fetch_task``
    """

    def __init__(
        self,
        async_worker: AsyncWorker,
        url_parser: URLParser,
        user_home_crawler: UserHomeCrawler,
        cookie_tester: CookieTester,
        cookie_repository: CookieRepository,
        worker_signals: WorkerSignals,
        control_signals: ControlSignals,
        parent=None,
    ) -> None:
        """初始化爬虫桥接器。

        Args:
            async_worker: 异步工作线程
            url_parser: 链接解析器
            user_home_crawler: 用户主页抓取器
            cookie_tester: Cookie 测试器
            cookie_repository: Cookie 仓库
            worker_signals: 工作线程→UI 信号
            control_signals: UI→工作线程控制信号
            parent: Qt 父对象
        """
        super().__init__(parent)
        self._async_worker = async_worker
        self._url_parser = url_parser
        self._user_home_crawler = user_home_crawler
        self._cookie_tester = cookie_tester
        self._cookie_repo = cookie_repository
        self._worker_signals = worker_signals
        self._control_signals = control_signals

        # 用于取消的 Task 引用
        self._parse_task: asyncio.Task | None = None
        self._home_fetch_task: asyncio.Task | None = None

        self._connect_signals()

    # === UI 控制信号槽 ===

    def on_start_parse(self, text: str) -> None:
        """接收 ``control_signals.start_parse``：启动链接解析。

        若已有解析任务在跑则先取消。

        Args:
            text: 用户粘贴的链接文本
        """
        self._async_worker.submit(self._handle_start_parse(text))

    def on_cancel_parse(self) -> None:
        """接收 ``control_signals.cancel_parse``：取消正在进行的解析。"""
        self._async_worker.submit(self._handle_cancel_parse())

    def on_start_home_fetch(self, sec_user_id: str, filters: dict) -> None:
        """接收 ``control_signals.start_home_fetch``：启动主页抓取。

        Args:
            sec_user_id: 用户 sec_user_id
            filters: dict 形式过滤条件，含 type_filter/max_count/start_date/end_date
        """
        self._async_worker.submit(self._handle_start_home_fetch(sec_user_id, filters))

    def on_cancel_home_fetch(self) -> None:
        """接收 ``control_signals.cancel_home_fetch``：取消正在进行的主页抓取。"""
        self._async_worker.submit(self._handle_cancel_home_fetch())

    def on_test_cookie(self, cookie_id: int) -> None:
        """接收 ``control_signals.test_cookie``：测试单条 Cookie。

        Args:
            cookie_id: Cookie ID
        """
        self._async_worker.submit(self._do_test_cookie(cookie_id))

    def on_test_all_cookies(self) -> None:
        """接收 ``control_signals.test_all_cookies``：测试所有 Cookie。"""
        self._async_worker.submit(self._do_test_all_cookies())

    # === 内部协程：链接解析 ===

    async def _handle_start_parse(self, text: str) -> None:
        """处理启动解析：先取消旧任务，再创建新任务。"""
        if self._parse_task is not None and not self._parse_task.done():
            self._parse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._parse_task
        self._parse_task = asyncio.ensure_future(self._do_parse(text))

    async def _handle_cancel_parse(self) -> None:
        """处理取消解析。"""
        if self._parse_task is not None and not self._parse_task.done():
            self._parse_task.cancel()
        self._parse_task = None

    async def _do_parse(self, text: str) -> None:
        """工作线程执行链接解析。

        多链接文本逐行解析，报告进度，完成后发射 ``parse_completed``。
        异常时发射 ``parse_failed``。取消时不发射失败信号。

        Args:
            text: 用户粘贴的链接文本
        """
        try:
            lines = text.strip().splitlines()
            links = [line.strip() for line in lines if line.strip()]
            total = len(links)
            results = []
            for i, line in enumerate(links, start=1):
                parsed = await self._url_parser.parse(line)
                results.append(parsed)
                self._worker_signals.parse_progress.emit(i, total)
            self._worker_signals.parse_completed.emit(results)
            logger.info("链接解析完成，共 %d 条", len(results))
        except asyncio.CancelledError:
            logger.info("链接解析被取消")
            raise
        except Exception as e:
            logger.exception("链接解析失败")
            self._worker_signals.parse_failed.emit(str(e))

    # === 内部协程：主页抓取 ===

    async def _handle_start_home_fetch(self, sec_user_id: str, filters: dict) -> None:
        """处理启动主页抓取：先取消旧任务，再创建新任务。"""
        if self._home_fetch_task is not None and not self._home_fetch_task.done():
            self._home_fetch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._home_fetch_task
        home_filters = HomeFilters(
            type_filter=filters.get("type_filter", "all"),
            max_count=filters.get("max_count", 0),
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
        )
        self._home_fetch_task = asyncio.ensure_future(
            self._do_home_fetch(sec_user_id, home_filters)
        )

    async def _handle_cancel_home_fetch(self) -> None:
        """处理取消主页抓取。"""
        if self._home_fetch_task is not None and not self._home_fetch_task.done():
            self._home_fetch_task.cancel()
        self._home_fetch_task = None

    async def _do_home_fetch(self, sec_user_id: str, filters: HomeFilters) -> None:
        """工作线程执行主页抓取。

        从 Cookie 仓库取一条 valid Cookie，调用 ``fetch_user_posts`` 迭代收集结果。
        完成后发射 ``home_fetch_completed``。异常时发射 ``home_fetch_failed``。

        Args:
            sec_user_id: 用户 sec_user_id
            filters: 过滤条件
        """
        try:
            cookie_record = self._cookie_repo.get_valid()
            if cookie_record is None:
                self._worker_signals.home_fetch_failed.emit("无可用 Cookie，请先添加")
                return
            cookie_content = cookie_record.content

            posts: list[PostItem] = []
            async for post in self._user_home_crawler.fetch_user_posts(
                sec_user_id,
                filters,
                cookie_content,
                progress_callback=self._on_home_fetch_progress,
            ):
                posts.append(post)
            self._worker_signals.home_fetch_completed.emit(posts)
            logger.info("主页抓取完成，共 %d 条作品", len(posts))
        except asyncio.CancelledError:
            logger.info("主页抓取被取消")
            raise
        except CookieInvalidError:
            logger.warning("主页抓取 Cookie 失效")
            self._worker_signals.home_fetch_failed.emit("Cookie 失效，请更新")
        except Exception as e:
            logger.exception("主页抓取失败")
            self._worker_signals.home_fetch_failed.emit(str(e))

    def _on_home_fetch_progress(self, fetched_count: int) -> None:
        """``UserHomeCrawler.fetch_user_posts`` 的 progress_callback。

        Args:
            fetched_count: 已抓取数量
        """
        self._worker_signals.home_fetch_progress.emit(fetched_count, 0)

    # === 内部协程：Cookie 测试 ===

    async def _do_test_cookie(self, cookie_id: int) -> None:
        """工作线程执行单条 Cookie 测试。

        Args:
            cookie_id: Cookie ID
        """
        try:
            cookie = self._cookie_repo.get_by_id(cookie_id)
            if cookie is None:
                self._worker_signals.cookie_test_result.emit(cookie_id, False, "Cookie 不存在")
                return
            result = await self._cookie_tester.test_cookie(cookie.content)
            self._worker_signals.cookie_test_result.emit(
                cookie_id, result.is_valid, result.error_message
            )
            logger.info("Cookie id=%s 测试完成，is_valid=%s", cookie_id, result.is_valid)
        except Exception as e:
            logger.exception("Cookie 测试异常")
            self._worker_signals.cookie_test_result.emit(cookie_id, False, str(e))

    async def _do_test_all_cookies(self) -> None:
        """工作线程执行全部 Cookie 测试。"""
        cookies = self._cookie_repo.get_all()
        for cookie in cookies:
            if cookie.id is None:
                continue
            await self._do_test_cookie(cookie.id)
        logger.info("全部 Cookie 测试完成，共 %d 条", len(cookies))

    # === 信号连接 ===

    def _connect_signals(self) -> None:
        """连接 UI → 工作线程控制信号到对应槽。"""
        self._control_signals.start_parse.connect(self.on_start_parse)
        self._control_signals.cancel_parse.connect(self.on_cancel_parse)
        self._control_signals.start_home_fetch.connect(self.on_start_home_fetch)
        self._control_signals.cancel_home_fetch.connect(self.on_cancel_home_fetch)
        self._control_signals.test_cookie.connect(self.on_test_cookie)
        self._control_signals.test_all_cookies.connect(self.on_test_all_cookies)
        logger.debug("CrawlerBridge 控制信号已连接")
