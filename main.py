"""抖音抓取器应用入口。

负责应用启动流程：日志初始化、目录确保、QApplication 创建、QSS 加载、
数据库初始化、AsyncWorker 与 Bridge 初始化、断点续传恢复、引导/主窗口显示、
退出清理。

严格遵循设计文档第 2.3 节（线程模型）与第 7.4 节（首次引导）。

启动流程::

    main()
      ├─ setup_logger()
      ├─ ensure_app_dirs()
      ├─ QApplication(sys.argv)
      ├─ _load_qss(app)
      ├─ conn = init_default_db()
      ├─ async_worker = AsyncWorker(); start()
      ├─ download_bridge, crawler_bridge = _create_bridges(conn, async_worker)
      ├─ download_bridge.restore_pending_tasks()
      ├─ ConfigRepository.get_onboarding_done() 判断
      ├─ MainWindow.show() 或引导占位
      ├─ exit_code = app.exec()
      └─ _cleanup(async_worker, conn)
"""

from __future__ import annotations

import contextlib
import sqlite3
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import config, database, logger
from app.logger import get_logger, setup_logger
from app.repositories import (
    ConfigRepository,
    CookieRepository,
    TaskItemRepository,
    TaskRepository,
)
from crawlers.cookie_tester import CookieTester
from crawlers.http_client import HttpClient
from crawlers.signer import Signer
from crawlers.url_parser import URLParser
from crawlers.user_home_crawler import UserHomeCrawler
from downloader.scheduler import Scheduler
from ui.main_window import APP_VERSION, MainWindow
from worker.async_worker import AsyncWorker
from worker.crawler_bridge import CrawlerBridge
from worker.download_bridge import DownloadBridge
from worker.signals import ControlSignals, WorkerSignals

# 模块级常量
APP_NAME = "抖音抓取器"
QSS_PATH = Path(__file__).parent / "ui" / "assets" / "style.qss"
ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"


def _load_qss(app: QApplication) -> None:
    """加载全局 QSS 样式表。

    文件不存在时记录警告日志但不阻断启动。

    Args:
        app: QApplication 实例。
    """
    try:
        qss_text = QSS_PATH.read_text(encoding="utf-8")
        app.setStyleSheet(qss_text)
        logger.info("QSS 样式表已加载: %s", QSS_PATH)
    except FileNotFoundError:
        logger.warning("QSS 样式表不存在: %s", QSS_PATH)


def _create_bridges(
    conn: sqlite3.Connection, async_worker: AsyncWorker
) -> tuple[DownloadBridge, CrawlerBridge]:
    """创建并装配 DownloadBridge 与 CrawlerBridge。

    组装完整依赖图：Repository → Signer → HttpClient → 各爬虫组件 → Bridge。

    Args:
        conn: 数据库连接。
        async_worker: 异步工作线程。

    Returns:
        (download_bridge, crawler_bridge) 元组。
    """
    # Repository 层
    task_repo = TaskRepository(conn)
    task_item_repo = TaskItemRepository(conn)
    cookie_repo = CookieRepository(conn)

    # Signer + HttpClient
    signer = Signer()
    http_client = HttpClient(cookie_repo, signer)

    # Scheduler（下载引擎）
    scheduler = Scheduler(conn=conn, http_client=None)

    # 信号对象
    worker_signals = WorkerSignals()
    control_signals = ControlSignals()

    # DownloadBridge
    download_bridge = DownloadBridge(
        async_worker=async_worker,
        scheduler=scheduler,
        task_item_repository=task_item_repo,
        task_repository=task_repo,
        worker_signals=worker_signals,
        control_signals=control_signals,
    )

    # 爬虫层组件
    url_parser = URLParser(http_client)
    user_home_crawler = UserHomeCrawler(http_client, signer)
    cookie_tester = CookieTester(http_client, signer)

    # CrawlerBridge（复用同一组信号对象）
    crawler_bridge = CrawlerBridge(
        async_worker=async_worker,
        url_parser=url_parser,
        user_home_crawler=user_home_crawler,
        cookie_tester=cookie_tester,
        cookie_repository=cookie_repo,
        worker_signals=worker_signals,
        control_signals=control_signals,
    )

    return download_bridge, crawler_bridge


def _cleanup(async_worker: AsyncWorker, conn: sqlite3.Connection) -> None:
    """退出清理：停止 AsyncWorker、关闭数据库连接。

    Args:
        async_worker: 异步工作线程。
        conn: 数据库连接。
    """
    logger.info("应用退出清理开始")
    async_worker.stop()
    with contextlib.suppress(sqlite3.Error):
        conn.close()
    logger.info("应用退出清理完成")


def main() -> None:
    """应用入口主流程。"""
    # 1. 日志初始化
    setup_logger()
    log = get_logger(__name__)
    log.info("=== %s %s 启动 ===", APP_NAME, APP_VERSION)

    # 2. 目录确保
    config.ensure_app_dirs()

    # 3. QApplication 创建
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # 4. QSS 加载
    _load_qss(app)

    # 5. 应用图标（文件存在时设置）
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    # 6. 数据库初始化
    conn = database.init_default_db()
    log.info("数据库已初始化: %s", config.DB_PATH)

    # 7. AsyncWorker 初始化
    async_worker = AsyncWorker()
    async_worker.start()
    log.info("AsyncWorker 已启动")

    # 8. Bridge 初始化
    download_bridge, crawler_bridge = _create_bridges(conn, async_worker)
    log.info("Bridge 已初始化")

    # 9. 断点续传恢复
    download_bridge.restore_pending_tasks()

    # 10. 引导判断
    config_repo = ConfigRepository(conn)
    onboarding_done = config_repo.get_onboarding_done()

    # 11. 窗口显示
    if onboarding_done:
        main_window = MainWindow(conn, download_bridge, crawler_bridge)
        main_window.show()
        log.info("主窗口已显示")
    else:
        # TODO(v0.0.8): 引导页完整流程实现，本里程碑临时显示主窗口
        log.warning("首次引导未完成，临时显示主窗口（引导页 v0.0.8 实现）")
        main_window = MainWindow(conn, download_bridge, crawler_bridge)
        main_window.show()

    # 12. 事件循环
    exit_code = app.exec()

    # 13. 退出清理
    _cleanup(async_worker, conn)
    log.info("=== %s 退出，code=%s ===", APP_NAME, exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log = get_logger(__name__)
        log.exception("应用启动失败")
        sys.exit(1)
