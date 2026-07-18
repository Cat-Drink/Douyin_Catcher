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

from ui.main_window import DEFAULT_WINDOW_SIZE, MIN_WINDOW_SIZE, MainWindow
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
        """v0.1.1：非客户区标题栏文字已移除，windowTitle() 为空字符串。"""
        assert main_window.windowTitle() == ""

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


class TestNavBarStatus:
    """v0.1.2：NavBar 底部下载任务状态栏测试。"""

    def test_nav_bar_has_status_label(self, qapp) -> None:
        """NavBar 含 _status_label 成员，初始显示"总数 0 · 下载中 0 · 已完成 0 · 失败 0"。"""
        nav_bar = NavBar()
        assert nav_bar._status_label is not None
        text = nav_bar._status_label.text()
        assert "总数 0" in text
        assert "下载中 0" in text
        assert "已完成 0" in text
        assert "失败 0" in text

    def test_nav_bar_update_status(self, qapp) -> None:
        """update_status 更新 NavBar 底部状态栏文字。"""
        nav_bar = NavBar()
        nav_bar.update_status(10, 3, 5, 2)
        text = nav_bar._status_label.text()
        assert "总数 10" in text
        assert "下载中 3" in text
        assert "已完成 5" in text
        assert "失败 2" in text

    def test_main_window_no_qstatusbar(self, main_window: MainWindow) -> None:
        """v0.1.2：QMainWindow QStatusBar 已移除，statusBar() 返回空 QStatusBar。

        QMainWindow.statusBar() 首次调用会创建空 QStatusBar（Qt 行为），
        但本应用不再调用 setStatusBar，也无 _status_counts_label 成员。
        """
        assert not hasattr(main_window, "_status_counts_label")
        assert not hasattr(main_window, "update_status_counts")

    def test_main_window_refresh_nav_status(self, main_window: MainWindow) -> None:
        """v0.1.2：_refresh_nav_status 从 DB 统计并刷新 NavBar 状态栏。

        MainWindow 构造时已调用 _refresh_nav_status()，mock_conn 下各
        get_by_status 返回空列表，NavBar 状态栏显示"总数 0"。
        """
        assert hasattr(main_window, "_refresh_nav_status")
        assert hasattr(main_window, "_schedule_nav_status_refresh")
        assert main_window._nav_status_timer is not None
        assert main_window._nav_bar is not None
        assert main_window._nav_bar._status_label is not None
        # 构造时已调用 _refresh_nav_status，mock 返回空列表
        assert "总数 0" in main_window._nav_bar._status_label.text()


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


# ==================== FetchPage 信号载荷测试（v0.1.4） ====================


class TestFetchPageDownloadSignal:
    """v0.1.4：FetchPage.download_requested 信号载荷为 list[dict] 测试。"""

    def test_download_signal_emits_list_of_dicts(
        self, qapp, mock_conn, mock_crawler_bridge
    ) -> None:
        """勾选项点击"开始下载"后，信号载荷为 list[dict]，含 aweme_id/title/cover_url 等字段。"""
        page = FetchPage(mock_crawler_bridge, mock_conn)
        # 模拟解析结果：构造 2 个 result dict 加入列表
        results = [
            {
                "aweme_id": "aweme_001",
                "title": "测试视频一",
                "author": "作者A",
                "type": "video",
                "duration": "00:15",
                "image_count": None,
                "cover_url": "https://example.com/cover1.jpg",
            },
            {
                "aweme_id": "aweme_002",
                "title": "测试视频二",
                "author": "作者B",
                "type": "image_set",
                "duration": None,
                "image_count": 9,
                "cover_url": "https://example.com/cover2.jpg",
            },
        ]
        for r in results:
            page._add_result_widget(r)

        captured: list = []
        page.download_requested.connect(lambda items: captured.append(items))

        # 全选并点击下载
        page._select_all_chk.setChecked(True)
        page._on_download_clicked()

        assert len(captured) == 1
        emitted = captured[0]
        assert isinstance(emitted, list)
        assert len(emitted) == 2
        assert all(isinstance(item, dict) for item in emitted)
        assert emitted[0]["aweme_id"] == "aweme_001"
        assert emitted[0]["title"] == "测试视频一"
        assert emitted[0]["cover_url"] == "https://example.com/cover1.jpg"
        assert emitted[1]["aweme_id"] == "aweme_002"
        assert emitted[1]["cover_url"] == "https://example.com/cover2.jpg"
        page.deleteLater()

    def test_download_signal_empty_when_no_selection(
        self, qapp, mock_conn, mock_crawler_bridge
    ) -> None:
        """无勾选时点击下载不发射信号。"""
        page = FetchPage(mock_crawler_bridge, mock_conn)
        page._add_result_widget(
            {
                "aweme_id": "aweme_x",
                "title": "x",
                "author": "",
                "type": "video",
                "duration": None,
                "image_count": None,
                "cover_url": "",
            }
        )
        captured: list = []
        page.download_requested.connect(lambda items: captured.append(items))
        # 不勾选，直接点击下载
        page._on_download_clicked()
        assert captured == []
        page.deleteLater()

    def test_result_item_widget_exposes_result_data(
        self, qapp, mock_conn, mock_crawler_bridge
    ) -> None:
        """ResultItemWidget.result_data 返回完整 dict（v0.1.4）。"""
        from ui.pages.fetch_page import ResultItemWidget

        result = {
            "aweme_id": "aweme_99",
            "title": "标题",
            "author": "作者",
            "type": "video",
            "duration": "00:30",
            "image_count": None,
            "cover_url": "https://example.com/c.jpg",
        }
        widget = ResultItemWidget(result)
        assert widget.result_data == result
        assert widget.aweme_id == "aweme_99"
        widget.deleteLater()
