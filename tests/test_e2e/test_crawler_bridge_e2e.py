"""CrawlerBridge 真实解析与主页抓取端到端测试。

验证 CrawlerBridge 通过真实 URLParser/UserHomeCrawler/CookieTester 组件，
在 AsyncWorker 后台线程中完成链接解析、主页抓取、Cookie 测试的完整链路。
需要真实 Cookie（.test_cookie.txt）、真实 aweme_id（.test_aweme_id.txt）、
真实 sec_user_id（.test_sec_user_id.txt）。
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.models import Cookie
from app.repositories import CookieRepository
from crawlers.cookie_tester import CookieTester
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.user_home_crawler import UserHomeCrawler
from worker.async_worker import AsyncWorker
from worker.crawler_bridge import CrawlerBridge
from worker.signals import ControlSignals, WorkerSignals

pytestmark = pytest.mark.integration

# 等待异步信号的最长秒数
_WAIT_TIMEOUT = 60.0

# 项目根目录（与 conftest 保持一致）
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent


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


def _assemble_bridge(clean_db: sqlite3.Connection, real_cookie: str):
    """组装真实爬虫组件 + CrawlerBridge。

    注入 Cookie 到 CookieRepository（status=valid），构造 Signer/HttpClient/
    URLParser/UserHomeCrawler/CookieTester，创建 AsyncWorker + CrawlerBridge。

    返回 (bridge, worker, http_client, cookie_repo, cookie_id)。
    调用方负责 worker.stop() 与 http_client.close()。
    """
    cookie_repo = CookieRepository(clean_db)
    cookie_id = cookie_repo.add(
        Cookie(
            id=None,
            content=real_cookie,
            label="e2e",
            status="valid",
            fail_count=0,
            created_at="",
        )
    )
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)
    user_home_crawler = UserHomeCrawler(http_client, signer)
    cookie_tester = CookieTester(http_client, signer)

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
    return bridge, worker, http_client, cookie_repo, cookie_id


async def test_crawler_bridge_parse_e2e(
    real_cookie: str,
    real_aweme_id: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """链接解析端到端：真实 URLParser 解析抖音视频链接。"""
    bridge, worker, http_client, _, _ = _assemble_bridge(clean_db, real_cookie)

    try:
        completed: list[list] = []
        failed: list[str] = []
        bridge._worker_signals.parse_completed.connect(completed.append)
        bridge._worker_signals.parse_failed.connect(failed.append)

        share_url = f"https://www.douyin.com/video/{real_aweme_id}"
        bridge.on_start_parse(share_url)

        await _wait_for(lambda: bool(completed) or bool(failed), qapp)

        assert not failed, f"解析失败: {failed[0] if failed else ''}"
        assert len(completed) == 1
        assert len(completed[0]) == 1
        parsed = completed[0][0]
        assert parsed.aweme_id == real_aweme_id
    finally:
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 worker.stop() 之前通过 submit() 在 worker 线程内关闭
        future = worker.submit(http_client.close())
        future.result(timeout=10)
        worker.stop()


async def test_crawler_bridge_home_fetch_e2e(
    real_cookie: str,
    real_sec_user_id: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """主页抓取端到端：真实 UserHomeCrawler 抓取作品列表。"""
    bridge, worker, http_client, _, _ = _assemble_bridge(clean_db, real_cookie)

    try:
        completed: list[list] = []
        failed: list[str] = []
        bridge._worker_signals.home_fetch_completed.connect(completed.append)
        bridge._worker_signals.home_fetch_failed.connect(failed.append)

        bridge.on_start_home_fetch(real_sec_user_id, {"type_filter": "all", "max_count": 3})

        await _wait_for(lambda: bool(completed) or bool(failed), qapp)

        assert not failed, f"主页抓取失败: {failed[0] if failed else ''}"
        assert len(completed) == 1
        posts = completed[0]
        assert len(posts) > 0, "未抓取到任何作品"
        for post in posts:
            assert post.aweme_id
    finally:
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 worker.stop() 之前通过 submit() 在 worker 线程内关闭
        future = worker.submit(http_client.close())
        future.result(timeout=10)
        worker.stop()


async def test_crawler_bridge_cookie_test_e2e(
    real_cookie: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """Cookie 测试端到端：真实 CookieTester 验证 Cookie 有效性。"""
    bridge, worker, http_client, _, cookie_id = _assemble_bridge(clean_db, real_cookie)

    try:
        results: list[tuple[int, bool, str]] = []
        bridge._worker_signals.cookie_test_result.connect(
            lambda cid, valid, msg: results.append((cid, valid, msg))
        )

        bridge.on_test_cookie(cookie_id)

        await _wait_for(lambda: bool(results), qapp)

        assert len(results) == 1
        cid, valid, msg = results[0]
        assert cid == cookie_id
        assert valid is True, f"Cookie 测试未通过: {msg}"
    finally:
        # http_client 绑定到 worker 线程的 event loop，
        # 必须在 worker.stop() 之前通过 submit() 在 worker 线程内关闭
        future = worker.submit(http_client.close())
        future.result(timeout=10)
        worker.stop()
