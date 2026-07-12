"""AsyncWorker 真实线程切换端到端测试（骨架）。

验证 ``AsyncWorker`` 在真实后台线程中运行 ``asyncio`` 事件循环，
UI 线程通过 ``submit()`` 把协程调度到工作线程执行真实的抖音链接解析任务，
并确认：

    1. 协程确实在 worker 线程执行（执行线程 ID 与主线程不同）
    2. 真实 ``URLParser`` 解析结果正确（aweme_id 匹配）

需要真实 Cookie（``.test_cookie.txt``）与真实 aweme_id（``.test_aweme_id.txt``）。
``AsyncWorker`` 继承自 ``QThread``，需要 ``QApplication``（由 pytest-qt 的 ``qapp``
fixture 提供）。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading

import pytest

from app.models import Cookie
from app.repositories import CookieRepository
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from worker.async_worker import AsyncWorker

pytestmark = pytest.mark.integration


async def test_async_worker_real_thread_e2e(
    real_cookie: str,
    real_aweme_id: str,
    clean_db: sqlite3.Connection,
    qapp,
) -> None:
    """AsyncWorker 真实线程切换：在 worker 线程执行真实 URL 解析任务。

    流程：
        1. 组装真实组件（CookieRepository 注入 Cookie / Signer / HttpClient / URLParser）
        2. 创建并启动 ``AsyncWorker``（后台线程 + asyncio loop）
        3. 通过 ``submit()`` 把解析协程调度到 worker 线程执行
        4. 验证执行线程 ID 与主线程不同、解析结果 aweme_id 匹配
        5. 清理：在 worker 线程关闭 http_client，再停止 worker
    """
    # 1. 组装真实组件：CookieRepository 注入真实 Cookie
    cookie_repo = CookieRepository(clean_db)
    cookie_repo.add(Cookie(id=None, content=real_cookie, status="valid"))
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)
    url_parser = URLParser(http_client)

    # 2. 创建并启动 AsyncWorker（后台线程 + 独立 asyncio loop）
    worker = AsyncWorker()
    worker.start()

    main_thread_id = threading.get_ident()
    exec_thread_id: dict[str, int | None] = {}

    async def parse_task():
        # 记录协程实际执行所在线程 ID，用于验证线程切换
        exec_thread_id["tid"] = threading.current_thread().ident
        share_url = f"https://www.douyin.com/video/{real_aweme_id}"
        return await url_parser.parse(share_url)

    try:
        # 3. submit 协程到 worker 线程的 loop，桥接到测试事件循环异步等待
        future = worker.submit(parse_task())
        parsed = await asyncio.wait_for(asyncio.wrap_future(future), timeout=30)

        # 4. 验证：任务在 worker 线程执行 & 解析结果正确
        worker_tid = exec_thread_id["tid"]
        assert worker_tid is not None, "未记录 worker 线程 ID"
        assert worker_tid != main_thread_id, "任务应在 worker 线程执行，而非主线程"
        assert parsed.aweme_id == real_aweme_id
        assert parsed.type == "video"

        # 5. 清理：httpx 客户端绑定在 worker loop 上，须在 worker 线程关闭
        close_future = worker.submit(http_client.close())
        await asyncio.wait_for(asyncio.wrap_future(close_future), timeout=5)
    finally:
        worker.stop()
