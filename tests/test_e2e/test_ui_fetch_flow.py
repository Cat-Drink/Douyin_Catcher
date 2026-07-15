"""UI FetchPage 解析流程端到端测试。

验证 FetchPage 通过真实 CrawlerBridge 解析抖音视频链接的完整 UI 链路：
点击"开始解析"按钮 → parse_requested 信号 → CrawlerBridge.on_start_parse →
URLParser → WorkerSignals.parse_completed → FetchPage.on_parse_completed →
结果列表渲染。

需要真实 Cookie（.test_cookie.txt）、真实 aweme_id（.test_aweme_id.txt）。
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3

import pytest

from app.models import Cookie
from app.repositories import CookieRepository
from crawlers.cookie_tester import CookieTester
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.user_home_crawler import UserHomeCrawler
from ui.pages.fetch_page import FetchPage
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
    raise AssertionError(f"等待条件超时（{timeout}s）")


async def test_ui_fetch_page_parse_e2e(
    real_cookie: str,
    real_aweme_id: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """UI 解析流程端到端：FetchPage 点击解析按钮，渲染真实解析结果。

    链路：FetchPage.parse_requested → ControlSignals.start_parse →
    CrawlerBridge.on_start_parse → URLParser → WorkerSignals.parse_completed →
    FetchPage.on_parse_completed → 结果列表渲染。
    """
    # 注入 Cookie 到 CookieRepository
    cookie_repo = CookieRepository(clean_db)
    cookie_repo.add(
        Cookie(
            id=None,
            content=real_cookie,
            label="e2e",
            status="valid",
            fail_count=0,
            created_at="",
        )
    )

    # 组装真实爬虫组件
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

    try:
        # 监听 Bridge 的完成/失败信号（用于判定解析结束）
        completed: list[list] = []
        failed: list[str] = []
        bridge._worker_signals.parse_completed.connect(completed.append)
        bridge._worker_signals.parse_failed.connect(failed.append)

        # 创建 FetchPage（构造时自动连接 worker_signals → on_parse_completed 等槽）
        page = FetchPage(bridge, clean_db)

        # 连接页面信号 → Bridge 控制信号（模拟 BridgeConnections 的粘合）
        page.parse_requested.connect(control_signals.start_parse.emit)

        # 在输入框中设置分享链接
        share_url = f"https://www.douyin.com/video/{real_aweme_id}"
        page._input_edit.setPlainText(share_url)

        # 点击"开始解析"按钮触发解析
        page._parse_btn.click()

        # 等待解析完成或失败（期间处理 Qt 事件以投递跨线程信号）
        await _wait_for(lambda: bool(completed) or bool(failed), qapp)
        qapp.processEvents()

        # 验证 Bridge 信号：解析成功
        assert not failed, f"解析失败: {failed[0] if failed else ''}"
        assert len(completed) == 1
        assert len(completed[0]) == 1
        assert completed[0][0].aweme_id == real_aweme_id

        # 验证 FetchPage 渲染了解析结果（结果列表非空）
        assert len(page._result_widgets) == 1
        assert page._result_widgets[0].aweme_id == real_aweme_id
    finally:
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 worker.stop() 之前通过 submit() 在 worker 线程内关闭
        with contextlib.suppress(Exception):
            worker.submit(http_client.close()).result(timeout=10)
        worker.stop()
