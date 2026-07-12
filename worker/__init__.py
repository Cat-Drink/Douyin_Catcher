"""工作线程层包。

提供 UI 线程与后台 asyncio 工作线程之间的桥接，包含：
- ``AsyncWorker``：QThread + asyncio loop 后台线程
- ``WorkerSignals`` / ``ControlSignals``：跨线程 Qt 信号
- ``DownloadBridge``：下载引擎桥接器
- ``CrawlerBridge``：爬虫层桥接器
"""

from __future__ import annotations

from worker.async_worker import LOOP_READY_TIMEOUT, STOP_TIMEOUT, AsyncWorker
from worker.crawler_bridge import CrawlerBridge
from worker.download_bridge import DownloadBridge
from worker.signals import ControlSignals, WorkerSignals

__all__ = [
    "AsyncWorker",
    "CrawlerBridge",
    "ControlSignals",
    "DownloadBridge",
    "LOOP_READY_TIMEOUT",
    "STOP_TIMEOUT",
    "WorkerSignals",
]
