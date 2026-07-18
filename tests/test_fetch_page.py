"""FetchPage 抓取页单元测试。

v0.1.6：覆盖抓取页交互优化三项任务：
    - 任务 1：全选联动逻辑（三态复选框 + 单项勾选同步全选）
    - 任务 2：提交下载后清理（download_started 信号触发清理）
    - 任务 3：取消解析时清理（保留输入文本，清空部分结果）

不依赖真实网络与真实 Bridge，使用 mock Bridge（附带真实 WorkerSignals）。
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from ui.pages.fetch_page import FetchPage
from worker.signals import ControlSignals, WorkerSignals

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
def mock_crawler_bridge() -> MagicMock:
    """返回 mock CrawlerBridge（附带真实 WorkerSignals）。"""
    return _make_mock_bridge()


@pytest.fixture
def fetch_page(qapp, mock_conn, mock_crawler_bridge) -> FetchPage:
    """构造 FetchPage 实例，yield 后删除。"""
    page = FetchPage(mock_crawler_bridge, mock_conn)
    yield page
    page.deleteLater()


def _make_result(aweme_id: str = "aweme_x", title: str = "标题") -> dict:
    """构造测试用结果 dict。"""
    return {
        "aweme_id": aweme_id,
        "title": title,
        "author": "作者",
        "type": "video",
        "duration": "00:15",
        "image_count": None,
        "cover_url": "https://example.com/c.jpg",
    }


# ==================== 任务 1：全选联动逻辑 ====================


class TestSelectAllTristate:
    """v0.1.6 任务 1：全选复选框三态联动测试。"""

    def test_select_all_tristate_enabled(self, fetch_page: FetchPage) -> None:
        """全选复选框已启用三态。"""
        assert fetch_page._select_all_chk.isTristate() is True

    def test_initial_state_unchecked(self, fetch_page: FetchPage) -> None:
        """无结果时全选状态为 Unchecked。"""
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Unchecked

    def test_select_all_checked_when_all_items_selected(self, fetch_page: FetchPage) -> None:
        """手动勾选全部 N 项时，全选自动变为 Checked（用户反馈 #4）。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        # 初始全选为 Unchecked
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Unchecked
        # 逐个勾选全部 3 项
        for widget in fetch_page._result_widgets:
            widget.set_selected(True)
        # 全选应自动变为 Checked
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Checked

    def test_select_all_partially_checked_when_some_items_selected(
        self, fetch_page: FetchPage
    ) -> None:
        """勾选部分项时，全选自动变为 PartiallyChecked（用户反馈 #4）。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        # 只勾选第一项
        fetch_page._result_widgets[0].set_selected(True)
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.PartiallyChecked

    def test_select_all_unchecked_when_no_items_selected(self, fetch_page: FetchPage) -> None:
        """取消全部项时，全选自动变为 Unchecked。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        # 先全选
        for widget in fetch_page._result_widgets:
            widget.set_selected(True)
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Checked
        # 再逐个取消
        for widget in fetch_page._result_widgets:
            widget.set_selected(False)
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Unchecked

    def test_click_select_all_checks_all_items(self, fetch_page: FetchPage) -> None:
        """点击全选复选框（设为 Checked）能勾选所有结果项。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        fetch_page._select_all_chk.setCheckState(Qt.CheckState.Checked)
        for widget in fetch_page._result_widgets:
            assert widget.is_selected() is True

    def test_click_select_all_unchecks_all_items(self, fetch_page: FetchPage) -> None:
        """点击全选复选框（设为 Unchecked）能取消所有结果项。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        # 先全选
        fetch_page._select_all_chk.setCheckState(Qt.CheckState.Checked)
        # 再取消
        fetch_page._select_all_chk.setCheckState(Qt.CheckState.Unchecked)
        for widget in fetch_page._result_widgets:
            assert widget.is_selected() is False

    def test_selected_count_updates_with_selection(self, fetch_page: FetchPage) -> None:
        """已选计数随勾选状态更新。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        # _add_result_widget 不自动更新计数，调用 _update_selected_count 同步
        fetch_page._update_selected_count()
        # 初始 0/3
        assert "已选 0 / 共 3 项" in fetch_page._selected_count_label.text()
        # 勾选 2 项
        fetch_page._result_widgets[0].set_selected(True)
        fetch_page._result_widgets[1].set_selected(True)
        assert "已选 2 / 共 3 项" in fetch_page._selected_count_label.text()
        # 下载按钮文案与启用状态
        assert "开始下载 (2)" in fetch_page._download_btn.text()
        assert fetch_page._download_btn.isEnabled() is True


# ==================== 任务 2：提交下载后清理 ====================


class TestClearAfterDownloadStarted:
    """v0.1.6 任务 2：download_started 信号触发清理测试。"""

    def test_clear_clears_input(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 清空输入框。"""
        fetch_page._input_edit.setPlainText("https://v.douyin.com/abc/")
        fetch_page.clear_after_download_started()
        assert fetch_page._input_edit.toPlainText() == ""

    def test_clear_clears_results(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 清空结果列表。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        assert len(fetch_page._result_widgets) == 3
        fetch_page.clear_after_download_started()
        assert len(fetch_page._result_widgets) == 0

    def test_clear_hides_filter_bar(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 隐藏过滤栏与主页提示行。"""
        fetch_page._home_hint_label.setVisible(True)
        fetch_page._filter_bar.setVisible(True)
        fetch_page.clear_after_download_started()
        # parent 未 show() 时 isVisible() 恒为 False，用 isHidden() 检查显式隐藏状态
        assert fetch_page._home_hint_label.isHidden() is True
        assert fetch_page._filter_bar.isHidden() is True

    def test_clear_resets_select_all(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 重置全选状态为 Unchecked。"""
        for i in range(3):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        fetch_page._select_all_chk.setCheckState(Qt.CheckState.Checked)
        fetch_page.clear_after_download_started()
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Unchecked

    def test_clear_resets_selected_count(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 重置已选计数为 0/0。"""
        for i in range(2):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        fetch_page._select_all_chk.setCheckState(Qt.CheckState.Checked)
        fetch_page.clear_after_download_started()
        assert "已选 0 / 共 0 项" in fetch_page._selected_count_label.text()
        assert "开始下载 (0)" in fetch_page._download_btn.text()
        assert fetch_page._download_btn.isEnabled() is False

    def test_clear_shows_empty_state(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 后显示空状态。"""
        for i in range(2):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        fetch_page.clear_after_download_started()
        # parent 未 show() 时 isVisible() 恒为 False，用 isHidden() 检查显式隐藏状态
        assert fetch_page._empty_widget.isHidden() is False
        assert fetch_page._scroll_area.isHidden() is True

    def test_clear_hides_input_error(self, fetch_page: FetchPage) -> None:
        """clear_after_download_started 隐藏输入错误提示。"""
        fetch_page._show_input_error("测试错误")
        assert fetch_page._input_error_label.isHidden() is False
        fetch_page.clear_after_download_started()
        assert fetch_page._input_error_label.isHidden() is True


# ==================== 任务 3：取消解析时清理 ====================


class TestCancelParseClears:
    """v0.1.6 任务 3：取消解析时清理部分结果测试。"""

    def test_cancel_parse_preserves_input_text(self, fetch_page: FetchPage) -> None:
        """解析中点取消，输入框文本保留（用户反馈 #5）。"""
        # 模拟解析中状态
        fetch_page._input_edit.setPlainText("https://v.douyin.com/abc/")
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        # 点击解析按钮（实际触发取消）
        fetch_page._parse_btn.click()
        # 输入框文本应保留
        assert fetch_page._input_edit.toPlainText() == "https://v.douyin.com/abc/"

    def test_cancel_parse_clears_partial_results(self, fetch_page: FetchPage) -> None:
        """解析中点取消，已解析的部分结果清空。"""
        # 模拟解析中已有部分结果
        for i in range(2):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        fetch_page._parse_btn.click()
        assert len(fetch_page._result_widgets) == 0

    def test_cancel_parse_resets_select_all(self, fetch_page: FetchPage) -> None:
        """解析中点取消，全选状态重置为 Unchecked。"""
        for i in range(2):
            fetch_page._add_result_widget(_make_result(aweme_id=f"a{i}"))
        fetch_page._select_all_chk.setCheckState(Qt.CheckState.Checked)
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        fetch_page._parse_btn.click()
        assert fetch_page._select_all_chk.checkState() == Qt.CheckState.Unchecked

    def test_cancel_parse_resets_parse_button(self, fetch_page: FetchPage) -> None:
        """解析中点取消，解析按钮恢复"开始解析"。"""
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        fetch_page._parse_btn.click()
        assert fetch_page._parse_btn.text() == "开始解析"

    def test_cancel_parse_emits_cancel_signal(self, fetch_page: FetchPage, qtbot) -> None:
        """解析中点取消，发射 cancel_parse_requested 信号。"""
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        with qtbot.waitSignal(fetch_page.cancel_parse_requested, timeout=1000):
            fetch_page._parse_btn.click()

    def test_cancel_parse_resets_is_parsing_flag(self, fetch_page: FetchPage) -> None:
        """解析中点取消，_is_parsing 标志复位为 False。"""
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        fetch_page._parse_btn.click()
        assert fetch_page._is_parsing is False

    def test_cancel_parse_hides_filter_bar(self, fetch_page: FetchPage) -> None:
        """解析中点取消，主页提示行与过滤栏隐藏。"""
        fetch_page._home_hint_label.setVisible(True)
        fetch_page._filter_bar.setVisible(True)
        fetch_page._is_parsing = True
        fetch_page._parse_btn.setText("解析中... 点击取消")
        fetch_page._parse_btn.click()
        assert fetch_page._home_hint_label.isHidden() is True
        assert fetch_page._filter_bar.isHidden() is True
