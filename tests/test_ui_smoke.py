"""UI 冒烟测试。

验证主窗口、导航栏、页面占位、状态栏、QSS 加载等基础功能。
使用 mock 数据库与 Bridge，避免依赖真实工作线程。

严格遵循设计文档 9.2 节（UI 层不强制覆盖率）与 v0.0.7 计划文档任务 7。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ui.main_window import APP_NAME, APP_VERSION, DEFAULT_WINDOW_SIZE, MIN_WINDOW_SIZE, MainWindow
from ui.pages.cookie_page import CookiePage
from ui.pages.download_page import DownloadPage
from ui.pages.fetch_page import FetchPage
from ui.pages.settings_page import SettingsPage
from ui.widgets.nav_bar import NavBar
from worker.signals import ControlSignals, WorkerSignals

# QSS 文件路径（与 main.py 一致）
_QSS_PATH = Path(__file__).parent.parent / "ui" / "assets" / "style.qss"


# ==================== Fixtures ====================


@pytest.fixture
def mock_conn() -> MagicMock:
    """返回 mock sqlite3.Connection。"""
    return MagicMock(spec=sqlite3.Connection)


def _make_mock_bridge() -> MagicMock:
    """构造 mock Bridge，附带真实 WorkerSignals。"""
    bridge = MagicMock()
    bridge._worker_signals = WorkerSignals()
    bridge._control_signals = ControlSignals()
    return bridge


@pytest.fixture
def mock_download_bridge() -> MagicMock:
    """返回 mock DownloadBridge（附带真实 WorkerSignals）。"""
    return _make_mock_bridge()


@pytest.fixture
def mock_crawler_bridge() -> MagicMock:
    """返回 mock CrawlerBridge（附带真实 WorkerSignals）。"""
    return _make_mock_bridge()


@pytest.fixture
def main_window(
    qapp, mock_conn: MagicMock, mock_download_bridge: MagicMock, mock_crawler_bridge: MagicMock
) -> MainWindow:
    """构造 MainWindow 实例，yield 后删除。

    不调用 close() 以避免触发 closeEvent 确认对话框。
    """
    window = MainWindow(mock_conn, mock_download_bridge, mock_crawler_bridge)
    yield window
    window.deleteLater()


# ==================== 主窗口测试 ====================


class TestMainWindow:
    """主窗口基础属性测试。"""

    def test_main_window_creation(
        self, qapp, mock_conn, mock_download_bridge, mock_crawler_bridge
    ) -> None:
        """MainWindow 可正常实例化，无异常抛出。"""
        window = MainWindow(mock_conn, mock_download_bridge, mock_crawler_bridge)
        assert window is not None
        window.deleteLater()

    def test_main_window_title(self, main_window: MainWindow) -> None:
        """窗口标题为"抖音抓取器"。"""
        assert main_window.windowTitle() == APP_NAME

    def test_main_window_minimum_size(self, main_window: MainWindow) -> None:
        """窗口最小尺寸为 800x600。"""
        assert main_window.minimumWidth() == MIN_WINDOW_SIZE[0]
        assert main_window.minimumHeight() == MIN_WINDOW_SIZE[1]

    def test_main_window_default_size(self, main_window: MainWindow) -> None:
        """窗口默认尺寸为 1280x800。"""
        assert main_window.width() == DEFAULT_WINDOW_SIZE[0]
        assert main_window.height() == DEFAULT_WINDOW_SIZE[1]


# ==================== 导航栏测试 ====================


class TestNavBar:
    """导航栏组件测试。"""

    def test_nav_bar_has_four_items(self, qapp) -> None:
        """NavBar 含 4 个导航项按钮。"""
        nav_bar = NavBar()
        # 通过 _nav_buttons 列表验证
        assert len(nav_bar._nav_buttons) == 4

    def test_nav_bar_page_changed_signal(self, qapp) -> None:
        """点击导航项时 page_changed 信号正确发射对应索引。"""
        nav_bar = NavBar()
        received: list[int] = []
        nav_bar.page_changed.connect(lambda idx: received.append(idx))

        # 模拟点击第二个导航项（index=1）
        nav_bar._nav_buttons[1].click()
        assert len(received) == 1
        assert received[0] == 1

    def test_nav_bar_set_current_page(self, qapp) -> None:
        """set_current_page 正确更新选中状态。"""
        nav_bar = NavBar()
        nav_bar.set_current_page(2)
        assert nav_bar._nav_buttons[2].isChecked() is True
        assert nav_bar._nav_buttons[0].isChecked() is False


# ==================== 页面切换测试 ====================


class TestPageSwitching:
    """导航切换与 QStackedWidget 联动测试。"""

    def test_stacked_widget_switches_on_nav(self, main_window: MainWindow) -> None:
        """导航切换时 QStackedWidget 当前索引正确更新。"""
        assert main_window._stacked_widget is not None
        # 初始为 index 0
        assert main_window._stacked_widget.currentIndex() == 0

        # 切换到 index 2
        main_window._nav_bar._nav_buttons[2].click()
        assert main_window._stacked_widget.currentIndex() == 2

    def test_stacked_widget_has_four_pages(self, main_window: MainWindow) -> None:
        """QStackedWidget 含 4 个页面。"""
        assert main_window._stacked_widget is not None
        assert main_window._stacked_widget.count() == 4


# ==================== 状态栏测试 ====================


class TestStatusBar:
    """状态栏显示测试。"""

    def test_status_bar_counts_display(self, main_window: MainWindow) -> None:
        """状态栏左侧初始显示"总数 0 · 下载中 0 · 已完成 0 · 失败 0"。"""
        assert main_window._status_counts_label is not None
        assert "总数 0" in main_window._status_counts_label.text()
        assert "下载中 0" in main_window._status_counts_label.text()
        assert "已完成 0" in main_window._status_counts_label.text()
        assert "失败 0" in main_window._status_counts_label.text()

    def test_status_bar_version_display(self, main_window: MainWindow) -> None:
        """状态栏右侧显示版本号。"""
        status_bar = main_window.statusBar()
        version_labels = status_bar.findChildren(type(main_window._status_counts_label))
        version_texts = [lbl.text() for lbl in version_labels]
        assert APP_VERSION in version_texts

    def test_update_status_counts(self, main_window: MainWindow) -> None:
        """update_status_counts 更新状态栏计数文本。"""
        main_window.update_status_counts(10, 3, 5, 2)
        assert main_window._status_counts_label is not None
        text = main_window._status_counts_label.text()
        assert "总数 10" in text
        assert "下载中 3" in text
        assert "已完成 5" in text
        assert "失败 2" in text


# ==================== QSS 加载测试 ====================


class TestQSS:
    """QSS 样式表加载测试。"""

    def test_qss_file_exists(self) -> None:
        """QSS 文件存在。"""
        assert _QSS_PATH.exists()

    def test_qss_file_not_empty(self) -> None:
        """QSS 文件内容非空。"""
        content = _QSS_PATH.read_text(encoding="utf-8")
        assert len(content.strip()) > 0

    def test_qss_loaded(self, qapp) -> None:
        """QApplication 加载 QSS 后 styleSheet() 非空。"""
        qss_text = _QSS_PATH.read_text(encoding="utf-8")
        qapp.setStyleSheet(qss_text)
        assert qapp.styleSheet() != ""


# ==================== 页面占位测试 ====================


class TestPages:
    """4 个页面占位骨架测试。"""

    def test_download_page_title(self, qapp, mock_conn, mock_download_bridge) -> None:
        """DownloadPage 顶部标题为"下载任务"。"""
        from PySide6.QtWidgets import QLabel

        page = DownloadPage(mock_download_bridge, mock_conn)
        labels = page.findChildren(QLabel)
        title_texts = [lbl.text() for lbl in labels]
        assert "下载任务" in title_texts

    def test_fetch_page_title(self, qapp, mock_conn, mock_crawler_bridge) -> None:
        """FetchPage 顶部标题为"链接抓取"。"""
        from PySide6.QtWidgets import QLabel

        page = FetchPage(mock_crawler_bridge, mock_conn)
        labels = page.findChildren(QLabel)
        title_texts = [lbl.text() for lbl in labels]
        assert "链接抓取" in title_texts

    def test_cookie_page_title(self, qapp, mock_conn, mock_crawler_bridge) -> None:
        """CookiePage 顶部标题为"Cookie 配置"。"""
        from PySide6.QtWidgets import QLabel

        page = CookiePage(mock_crawler_bridge, mock_conn)
        labels = page.findChildren(QLabel)
        title_texts = [lbl.text() for lbl in labels]
        assert "Cookie 配置" in title_texts

    def test_settings_page_title(self, qapp, mock_conn) -> None:
        """SettingsPage 顶部标题为"设置"。"""
        from PySide6.QtWidgets import QLabel

        page = SettingsPage(mock_conn)
        labels = page.findChildren(QLabel)
        title_texts = [lbl.text() for lbl in labels]
        assert "设置" in title_texts

    def test_pages_have_refresh_method(
        self, qapp, mock_conn, mock_download_bridge, mock_crawler_bridge
    ) -> None:
        """4 个 Page 类均实现 refresh() 方法，调用无异常。"""
        pages = [
            DownloadPage(mock_download_bridge, mock_conn),
            FetchPage(mock_crawler_bridge, mock_conn),
            CookiePage(mock_crawler_bridge, mock_conn),
            SettingsPage(mock_conn),
        ]
        for page in pages:
            assert hasattr(page, "refresh")
            # 调用 refresh 不应抛异常
            page.refresh()
