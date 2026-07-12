"""主窗口框架模块。

实现主窗口，包含左侧导航栏（200px）+ 右侧内容区（QStackedWidget，
4 个页面）+ 底部状态栏（32px）。

严格遵循 UI/UX 规范 5.1 节（主窗口框架）与 v0.0.7 计划文档任务 3。

布局结构::

    QMainWindow
      └─ centralWidget (QWidget)
           └─ QHBoxLayout
                ├─ NavBar (200px 固定)
                └─ QStackedWidget (自适应)
                     ├─ DownloadPage (index 0)
                     ├─ FetchPage (index 1)
                     ├─ CookiePage (index 2)
                     └─ SettingsPage (index 3)
      └─ QStatusBar
           ├─ QLabel#statusBarCounts (左侧)
           └─ QLabel#statusBarVersion (右侧)
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from app.logger import get_logger
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
APP_NAME = "抖音抓取器"
APP_VERSION = "v0.0.7"
MIN_WINDOW_SIZE = (800, 600)
DEFAULT_WINDOW_SIZE = (1280, 800)


class MainWindow(QMainWindow):
    """主窗口框架。

    组合 NavBar + QStackedWidget(4 页面) + QStatusBar，
    连接 NavBar.page_changed 信号切换页面。
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
        self._status_counts_label: QLabel | None = None
        self._bridge_connections: BridgeConnections | None = None
        self._error_handler: ErrorHandler | None = None
        self._pages: dict[str, QWidget] = {}

        self._setup_ui()
        self._setup_window()
        self._setup_status_bar()
        self._setup_connections()

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
        """设置窗口属性：标题、最小尺寸、推荐尺寸。"""
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        self.resize(*DEFAULT_WINDOW_SIZE)

    def _setup_status_bar(self) -> None:
        """创建底部状态栏：左侧计数 + 右侧版本号。"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self._status_counts_label = QLabel("总数 0 · 下载中 0 · 已完成 0 · 失败 0")
        self._status_counts_label.setObjectName("statusBarCounts")
        status_bar.addWidget(self._status_counts_label)

        version_label = QLabel(APP_VERSION)
        version_label.setObjectName("statusBarVersion")
        status_bar.addPermanentWidget(version_label)

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

    def update_status_counts(
        self, total: int, downloading: int, completed: int, failed: int
    ) -> None:
        """更新状态栏左侧计数文本。

        Args:
            total: 总任务数。
            downloading: 下载中数。
            completed: 已完成数。
            failed: 失败数。
        """
        if self._status_counts_label is None:
            return
        text = f"总数 {total} · 下载中 {downloading} · 已完成 {completed} · 失败 {failed}"
        self._status_counts_label.setText(text)

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
