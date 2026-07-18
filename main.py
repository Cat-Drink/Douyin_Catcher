"""抖音抓取器应用入口。

负责应用启动流程：日志初始化、目录确保、QApplication 创建、QSS 加载、
数据库初始化、AsyncWorker 与 Bridge 初始化、断点续传恢复、ErrorHandler 初始化、
全局异常捕获、引导/主窗口显示、退出清理。

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
      ├─ MainWindow + ErrorHandler + sys.excepthook 初始化
      ├─ ConfigRepository.get_onboarding_done() 判断
      ├─ onboarding_done → MainWindow.show()
      │  否则 → OnboardingPage.start() → 完成后 → MainWindow.show()
      ├─ exit_code = app.exec()
      └─ _cleanup(async_worker, conn)
"""

from __future__ import annotations

import contextlib
import sqlite3
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import config, database
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
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler
from ui.error_handler import ErrorHandler
from ui.main_window import APP_VERSION, MainWindow
from ui.pages.onboarding_page import OnboardingPage
from ui.widgets.toast import Toast
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
        log = get_logger(__name__)
        log.info("QSS 样式表已加载: %s", QSS_PATH)
    except FileNotFoundError:
        log = get_logger(__name__)
        log.warning("QSS 样式表不存在: %s", QSS_PATH)


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

    # 爬虫层组件（DownloadBridge 依赖 VideoParser，需先创建）
    url_parser = URLParser(http_client)
    user_home_crawler = UserHomeCrawler(http_client, signer)
    cookie_tester = CookieTester(http_client, signer)
    video_parser = VideoParser(http_client, signer)

    # DownloadBridge
    download_bridge = DownloadBridge(
        async_worker=async_worker,
        scheduler=scheduler,
        task_item_repository=task_item_repo,
        task_repository=task_repo,
        worker_signals=worker_signals,
        control_signals=control_signals,
        video_parser=video_parser,
        cookie_repository=cookie_repo,
    )

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
    log = get_logger(__name__)
    log.info("应用退出清理开始")
    async_worker.stop()
    with contextlib.suppress(sqlite3.Error):
        conn.close()
    log.info("应用退出清理完成")


def _install_excepthook(error_handler: ErrorHandler) -> None:
    """安装全局异常捕获钩子。

    捕获未处理的 Python 异常，记录完整栈到日志，并通过 ErrorHandler
    弹窗提示用户"未知错误"（含复制详情按钮）。

    Args:
        error_handler: 错误处理器实例。
    """

    def _excepthook(exc_type, exc_value, exc_tb) -> None:  # noqa: ANN001
        # 记录完整 traceback 到日志
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log = get_logger(__name__)
        log.error("未捕获异常:\n%s", tb_text)
        # 通过 ErrorHandler 弹窗提示用户
        error_handler.handle_error("unknown_error", {"details": tb_text})

    sys.excepthook = _excepthook


def _enter_main_window(
    main_window: MainWindow,
    onboarding_page: OnboardingPage,
    log,
    cookie_configured: bool = True,
) -> None:  # noqa: ANN001
    """引导完成后切换到主窗口。

    关闭引导页，显示主窗口。若跳过引导且未配置 Cookie，Toast 提示用户。

    Args:
        main_window: 主窗口实例。
        onboarding_page: 引导页实例。
        log: 日志记录器。
        cookie_configured: 是否已配置 Cookie（跳过引导时用）。
    """
    onboarding_page.close()
    onboarding_page.deleteLater()
    main_window.show()
    log.info("引导完成，主窗口已显示")
    if not cookie_configured:
        Toast.show_warning(main_window, "未配置 Cookie，部分功能不可用")


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

    # 8.1 启动 Scheduler 调度循环（必须在恢复任务前启动）
    download_bridge.init_scheduler(config.DEFAULT_CONCURRENCY)

    # 9. 断点续传恢复
    download_bridge.restore_pending_tasks()

    # 10. 引导判断
    config_repo = ConfigRepository(conn)
    cookie_repo = CookieRepository(conn)
    onboarding_done = config_repo.get_onboarding_done()

    # 11. 主窗口 + ErrorHandler 初始化
    main_window = MainWindow(conn, download_bridge, crawler_bridge)
    error_handler = ErrorHandler(main_window)
    main_window.set_error_handler(error_handler)

    # 12. 全局异常捕获
    _install_excepthook(error_handler)

    # 13. 窗口显示（引导判断）
    if onboarding_done:
        main_window.show()
        log.info("主窗口已显示（引导已完成）")
    else:
        # 首次启动：显示引导流程
        cookie_tester = crawler_bridge._cookie_tester  # noqa: SLF001
        onboarding_page = OnboardingPage(
            config_repo=config_repo,
            cookie_repo=cookie_repo,
            async_worker=async_worker,
            cookie_tester=cookie_tester,
            main_window=main_window,
            error_handler=error_handler,
        )
        onboarding_page.onboarding_completed.connect(
            lambda: _enter_main_window(main_window, onboarding_page, log)
        )
        onboarding_page.onboarding_skipped.connect(
            lambda configured: _enter_main_window(
                main_window, onboarding_page, log, cookie_configured=configured
            )
        )
        onboarding_page.start()
        log.info("引导流程已显示")

    # 14. 事件循环
    exit_code = app.exec()

    # 15. 退出清理
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
