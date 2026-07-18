"""UI CookiePage Cookie 管理端到端测试。

验证 CookiePage 通过真实 CrawlerBridge 组件，完成 Cookie 添加、测试触发、
测试结果回显的完整 UI 链路。需要真实 Cookie（.test_cookie.txt）。

严格遵循设计文档 9.1 节与 v0.0.x 计划文档。
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from app.models import Cookie
from app.repositories import CookieRepository
from crawlers.cookie_tester import CookieTester
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.user_home_crawler import UserHomeCrawler
from ui.pages.cookie_page import CookiePage
from worker.async_worker import AsyncWorker
from worker.crawler_bridge import CrawlerBridge
from worker.signals import ControlSignals, WorkerSignals

pytestmark = pytest.mark.integration

# 等待异步信号的最长秒数
_WAIT_TIMEOUT = 60.0


async def _wait_for(predicate, qapp, timeout: float = _WAIT_TIMEOUT) -> None:
    """轮询等待条件满足，期间定期处理 Qt 事件以投递跨线程信号。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        qapp.processEvents()
        if predicate():
            return
        await asyncio.sleep(0.5)
    qapp.processEvents()
    if predicate():
        return
    raise AssertionError(f"等待信号超时（{timeout}s）")


async def test_ui_cookie_page_test_e2e(
    real_cookie: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """UI CookiePage Cookie 测试端到端：添加 Cookie → 触发测试 → 显示有效状态。

    组装真实爬虫组件与 CrawlerBridge，创建 CookiePage，通过页面信号添加
    Cookie 并触发测试，验证 CookiePage 状态栏显示 Cookie 有效状态。
    """
    # 组装真实爬虫组件
    cookie_repo = CookieRepository(clean_db)
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    user_home_crawler = UserHomeCrawler(http_client, signer)
    cookie_tester = CookieTester(http_client, signer)

    # 创建 AsyncWorker + CrawlerBridge
    worker = AsyncWorker()
    worker.start()
    worker_signals = WorkerSignals()
    control_signals = ControlSignals()
    bridge = CrawlerBridge(
        async_worker=worker,
        url_parser=url_parser,
        user_home_crawler=user_home_crawler,
        cookie_tester=cookie_tester,
        cookie_repository=cookie_repo,
        worker_signals=worker_signals,
        control_signals=control_signals,
    )

    # 创建 CookiePage（构造时自动连接 bridge._worker_signals.cookie_test_result）
    page = CookiePage(bridge, clean_db)

    # 连接页面信号 → Bridge 控制信号（模拟 BridgeConnections 的粘合层）
    page.test_cookie_requested.connect(control_signals.test_cookie.emit)

    def _on_add_cookie(content: str, label: str) -> None:
        """添加 Cookie 信号槽：写入 DB 并刷新页面（模拟 BridgeConnections）。"""
        cookie_repo.add(Cookie(id=None, content=content, label=label or None))
        page.refresh()

    page.add_cookie_requested.connect(_on_add_cookie)

    try:
        # 通过 CookiePage 信号添加 Cookie
        page.add_cookie_requested.emit(real_cookie, "e2e-ui")
        qapp.processEvents()

        # 验证 Cookie 已添加到页面列表
        assert len(page._cookie_widgets) == 1, "Cookie 未添加到页面"
        cookie_id = next(iter(page._cookie_widgets.keys()))

        # 通过 CookiePage 信号触发 Cookie 测试
        page.test_cookie_requested.emit(cookie_id)

        # v0.1.2：CookiePage 底部状态栏已移除，改为通过 widget._cookie.status 验证
        await _wait_for(
            lambda: page._cookie_widgets[cookie_id]._cookie.status == "valid",
            qapp,
        )

        # 验证 CookieItemWidget 显示了有效状态
        widget = page._cookie_widgets[cookie_id]
        assert widget._cookie.status == "valid"
    finally:
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 worker.stop() 之前通过 submit() 在 worker 线程内关闭
        future = worker.submit(http_client.close())
        future.result(timeout=10)
        worker.stop()
        page.deleteLater()
