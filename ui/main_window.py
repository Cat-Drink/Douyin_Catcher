"""主窗口框架模块。

实现主窗口，包含左侧导航栏（200px，底部含下载任务状态栏与版本号）+
右侧内容区（QStackedWidget，4 个页面）。

严格遵循 UI/UX 规范 5.1 节（主窗口框架）与 v0.0.7 计划文档任务 3。
v0.1.2：移除 QMainWindow QStatusBar，状态栏统一移至 NavBar 底部；
        新增 _refresh_nav_status 从 DB 统计任务项并刷新 NavBar 状态栏，
        通过 QTimer 300ms 防抖避免 progress_updated 高频刷新。

布局结构::

    QMainWindow
      └─ centralWidget (QWidget)
           └─ QHBoxLayout
                ├─ NavBar (200px 固定)
                │    ├─ navLogo
                │    ├─ navItem × 4
                │    ├─ addStretch
                │    ├─ navStatusBar (下载任务统计)
                │    └─ navVersion
                └─ QStackedWidget (自适应)
                     ├─ DownloadPage (index 0)
                     ├─ FetchPage (index 1)
                     ├─ CookiePage (index 2)
                     └─ SettingsPage (index 3)
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from app.logger import get_logger
from app.repositories import TaskItemRepository
from ui.bridge_connections import BridgeConnections
from ui.pages.cookie_page import CookiePage
from ui.pages.download_page import DownloadPage
from ui.pages.fetch_page import FetchPage
from ui.pages.settings_page import SettingsPage
from ui.widgets.nav_bar import NavBar
from worker.crawler_bridge import CrawlerBridge
from worker.download_bridge import DownloadBridge

if TYPE_CHECKING:
    from ui.error_handler import ErrorHandler

logger = get_logger(__name__)

# 窗口属性常量（规范 5.1 节）
APP_NAME = "撷风拾影"
_APP_VERSION = "0.2.2"  # 版本号单一来源（规范 8.3 节），供 UI 模块引用以避免版本号漂移
APP_VERSION = f"v{_APP_VERSION}"  # 向后兼容别名，供 main.py 与测试引用
MIN_WINDOW_SIZE = (800, 600)
DEFAULT_WINDOW_SIZE = (1280, 800)

# v0.1.2：NavBar 状态栏刷新防抖间隔（毫秒）
# progress_updated 信号高频触发，防抖避免 UI 卡顿（计划 8.2.1 节）
_NAV_STATUS_DEBOUNCE_MS = 300

# 下载任务项状态枚举（与 DB task_items.status 字段一致）
_STATUS_DOWNLOADING = "downloading"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"


class MainWindow(QMainWindow):
    """主窗口框架。

    组合 NavBar（含底部状态栏）+ QStackedWidget(4 页面)，
    连接 NavBar.page_changed 信号切换页面，连接 Bridge WorkerSignals
    到 _refresh_nav_status 实时刷新 NavBar 底部状态栏。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        download_bridge: DownloadBridge,
        crawler_bridge: CrawlerBridge,
        parent: QWidget | None = None,
    ) -> None:
        """初始化主窗口。

        Args:
            conn: 数据库连接，传递给需要读写数据库的页面。
            download_bridge: 下载引擎桥接器。
            crawler_bridge: 爬虫层桥接器。
            parent: 父控件。
        """
        super().__init__(parent)
        self._conn = conn
        self._download_bridge = download_bridge
        self._crawler_bridge = crawler_bridge

        self._nav_bar: NavBar | None = None
        self._stacked_widget: QStackedWidget | None = None
        self._bridge_connections: BridgeConnections | None = None
        self._error_handler: ErrorHandler | None = None
        self._pages: dict[str, QWidget] = {}
        # v0.1.2：NavBar 状态栏防抖 QTimer，避免 progress_updated 高频刷新
        self._nav_status_timer: QTimer | None = None

        self._setup_ui()
        self._setup_window()
        self._setup_nav_status_refresh()
        self._setup_connections()
        # v0.1.2：启动时从 DB 加载初始统计，不依赖信号触发（计划 8.2.2 节）
        self._refresh_nav_status()

    def _setup_ui(self) -> None:
        """构建整体布局：导航栏 + 内容区。"""
        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧导航栏
        self._nav_bar = NavBar()
        self._nav_bar.page_changed.connect(self._on_page_changed)
        layout.addWidget(self._nav_bar)

        # 右侧内容区（QStackedWidget）
        self._stacked_widget = QStackedWidget()
        download_page = DownloadPage(self._download_bridge, self._conn)
        fetch_page = FetchPage(self._crawler_bridge, self._conn)
        cookie_page = CookiePage(self._crawler_bridge, self._conn)
        settings_page = SettingsPage(self._conn)
        self._stacked_widget.addWidget(download_page)  # index 0
        self._stacked_widget.addWidget(fetch_page)  # index 1
        self._stacked_widget.addWidget(cookie_page)  # index 2
        self._stacked_widget.addWidget(settings_page)  # index 3
        layout.addWidget(self._stacked_widget, 1)

        # 存储页面引用供 BridgeConnections 使用
        self._pages = {
            "download": download_page,
            "fetch": fetch_page,
            "cookie": cookie_page,
            "settings": settings_page,
        }

        self.setCentralWidget(central_widget)

        # 默认选中第一个导航项
        self._nav_bar.set_current_page(0)

    def _setup_window(self) -> None:
        """设置窗口属性：标题、最小尺寸、推荐尺寸。

        v0.1.1：移除非客户区标题栏文字，保留系统标题栏以保留拖动与
        最小化/最大化/关闭按钮（低风险方案，不使用 FramelessWindowHint）。
        """
        self.setWindowTitle("")  # 移除标题栏文字，保留系统按钮与拖动
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        self.resize(*DEFAULT_WINDOW_SIZE)

    def _setup_nav_status_refresh(self) -> None:
        """v0.1.2：创建 NavBar 状态栏防抖 QTimer 并连接 Bridge 信号。

        防抖机制：progress_updated 等信号高频触发时，仅保留最后一次触发后
        300ms 执行一次实际刷新，避免 UI 卡顿（计划 8.2.1 节）。
        """
        self._nav_status_timer = QTimer(self)
        self._nav_status_timer.setSingleShot(True)
        self._nav_status_timer.setInterval(_NAV_STATUS_DEBOUNCE_MS)
        self._nav_status_timer.timeout.connect(self._refresh_nav_status)

        # 连接 DownloadBridge WorkerSignals 到防抖刷新槽
        signals = self._download_bridge._worker_signals  # noqa: SLF001
        signals.progress_updated.connect(self._schedule_nav_status_refresh)
        signals.item_completed.connect(self._schedule_nav_status_refresh)
        signals.item_failed.connect(self._schedule_nav_status_refresh)
        signals.task_completed.connect(self._schedule_nav_status_refresh)
        logger.debug("NavBar 状态栏刷新信号已连接")

    def _schedule_nav_status_refresh(self, *args) -> None:
        """防抖触发 NavBar 状态栏刷新（忽略信号参数）。

        任意 Bridge 信号到达时启动/重启 300ms 定时器，仅最后一次触发后
        实际刷新一次。
        """
        if self._nav_status_timer is not None:
            self._nav_status_timer.start()

    def _refresh_nav_status(self) -> None:
        """v0.1.2：从 DB 统计任务项各状态数量，刷新 NavBar 底部状态栏。

        数据源为 TaskItemRepository.get_by_status，确保跨页面一致性
        （非下载页时也能实时显示）。状态枚举与 DB task_items.status 字段一致。

        异常处理：捕获 Exception 而非 sqlite3.Error，避免 row 解析失败等
        非预期异常导致 UI 崩溃（UI 刷新应 fail-silent）。
        """
        if self._nav_bar is None:
            return
        try:
            item_repo = TaskItemRepository(self._conn)
            downloading = len(item_repo.get_by_status(_STATUS_DOWNLOADING))
            completed = len(item_repo.get_by_status(_STATUS_COMPLETED))
            failed = len(item_repo.get_by_status(_STATUS_FAILED))
            # 总数 = 下载中 + 已完成 + 失败 + 待处理（pending/paused）
            pending = len(item_repo.get_by_status("pending"))
            paused = len(item_repo.get_by_status("paused"))
            total = downloading + completed + failed + pending + paused
        except Exception as e:  # noqa: BLE001 - UI 刷新 fail-silent
            logger.error("刷新 NavBar 状态栏失败: %s", e)
            return
        self._nav_bar.update_status(total, downloading, completed, failed)

    def _setup_connections(self) -> None:
        """创建 BridgeConnections 并连接所有 Bridge 信号。"""
        self._bridge_connections = BridgeConnections(
            main_window=self,
            download_bridge=self._download_bridge,
            crawler_bridge=self._crawler_bridge,
            pages=self._pages,
        )
        self._bridge_connections.setup_connections()

    def _on_page_changed(self, index: int) -> None:
        """导航切换回调：切换 QStackedWidget 当前页，调用页面 refresh()。

        Args:
            index: 目标页面索引。
        """
        assert self._stacked_widget is not None
        self._stacked_widget.setCurrentIndex(index)
        widget = self._stacked_widget.widget(index)
        if widget is not None and hasattr(widget, "refresh"):
            widget.refresh()
        logger.debug("切换到页面 index=%s", index)

    def set_error_handler(self, error_handler: ErrorHandler) -> None:
        """注入 ErrorHandler 实例。

        ErrorHandler 需要 MainWindow 引用，故在 MainWindow 构造后注入。

        Args:
            error_handler: 错误处理器实例。
        """
        self._error_handler = error_handler

    @property
    def error_handler(self) -> ErrorHandler | None:
        """返回已注入的 ErrorHandler 实例（未注入时为 None）。"""
        return self._error_handler

    def goto_cookie_page(self) -> None:
        """切换到 Cookie 配置页（导航索引 2）。"""
        if self._nav_bar is not None:
            self._nav_bar.set_current_page(2)
            logger.debug("已跳转到 Cookie 配置页")

    def goto_settings_page(self) -> None:
        """切换到设置页（导航索引 3）。"""
        if self._nav_bar is not None:
            self._nav_bar.set_current_page(3)
            logger.debug("已跳转到设置页")

    def closeEvent(self, event: QCloseEvent) -> None:
        """重写关闭事件：弹出确认退出对话框。

        用户确认则接受关闭事件，否则忽略。
        实际资源清理在 main.py 的 _cleanup 中完成。

        Args:
            event: 关闭事件。
        """
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出应用吗？下载中的任务将被暂停，下次启动可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("用户确认退出应用")
            event.accept()
        else:
            event.ignore()
