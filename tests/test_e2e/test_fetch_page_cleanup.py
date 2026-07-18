"""场景：抓取页提交下载后清理端到端测试（v0.1.6 / v0.1.8 plan 3）。

验证提交下载后抓取页内容被清理的完整 UI 链路：
    输入链接 -> 解析 -> 渲染结果 -> 勾选 -> 点击开始下载 ->
    DownloadBridge.download_started -> FetchPage.clear_after_download_started -> 抓取页清空

覆盖 v0.1.6 用户反馈 #6：提交后清理抓取页。

需要真实 Cookie（.test_cookie.txt）与真实 aweme_id（.test_aweme_id.txt）。
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

# 标记所有端到端测试为 integration（CI 默认跳过）
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


async def test_fetch_page_cleanup_after_submit(
    real_cookie: str,
    real_aweme_id: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """提交下载后抓取页清空：解析 -> 勾选 -> 点击开始下载 -> 验证抓取页清空。

    链路：FetchPage 解析 -> 渲染结果 -> 勾选 -> download_requested ->
    DownloadBridge.download_started -> FetchPage.clear_after_download_started。
    """
    # 1. 注入 Cookie
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

    # 2. 组装真实爬虫组件
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    user_home_crawler = UserHomeCrawler(http_client, signer)
    cookie_tester = CookieTester(http_client, signer)

    # 3. 创建 AsyncWorker + CrawlerBridge
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
        # 4. 监听解析完成/失败信号
        parse_completed: list[list] = []
        parse_failed: list[str] = []
        bridge._worker_signals.parse_completed.connect(parse_completed.append)
        bridge._worker_signals.parse_failed.connect(parse_failed.append)

        # 5. 创建 FetchPage
        page = FetchPage(bridge, clean_db)
        page.parse_requested.connect(control_signals.start_parse.emit)

        # 6. 输入链接并点击解析
        share_url = f"https://www.douyin.com/video/{real_aweme_id}"
        page._input_edit.setPlainText(share_url)
        page._parse_btn.click()

        # 7. 等待解析完成
        await _wait_for(lambda: bool(parse_completed) or bool(parse_failed), qapp)
        qapp.processEvents()

        assert not parse_failed, f"解析失败: {parse_failed[0] if parse_failed else ''}"
        assert len(parse_completed) == 1
        assert len(page._result_widgets) == 1

        # 8. 勾选结果项（默认已勾选，确保勾选状态）
        if page._result_widgets:
            page._result_widgets[0].set_selected(True)

        # 9. 监听 download_started 信号（触发清理）
        download_started: list[int] = []
        bridge._worker_signals.download_started.connect(download_started.append)

        # 10. 点击开始下载按钮
        page._download_btn.click()

        # 11. 等待 download_started 信号到达（会触发 clear_after_download_started）
        await _wait_for(lambda: bool(download_started), qapp, timeout=30.0)
        qapp.processEvents()

        # 12. 验证抓取页已清空
        assert page._input_edit.toPlainText() == "", "提交后输入框应清空"
        assert len(page._result_widgets) == 0, "提交后结果列表应清空"
        assert page._home_hint_label.isHidden(), "提交后主页提示行应隐藏"
        assert page._filter_bar.isHidden(), "提交后过滤栏应隐藏"
        from PySide6.QtCore import Qt

        assert (
            page._select_all_chk.checkState() == Qt.CheckState.Unchecked
        ), "提交后全选复选框应重置为未选"
    finally:
        with contextlib.suppress(Exception):
            worker.submit(http_client.close()).result(timeout=10)
        worker.stop()
