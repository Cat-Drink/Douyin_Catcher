"""下载任务页模块。

实现下载任务页，包含顶部批量操作工具栏、任务列表（可滚动）、
底部状态栏、空状态引导。接收 Bridge 的 progress_updated/item_completed/
item_failed 信号实时刷新。

严格遵循设计文档 3.1 节页面 1 与 UIUX 规范 5.2 节。

布局结构::

    [56px 标题区: "下载任务"]
    [48px 工具栏: 全部暂停 / 全部开始 / 清空已完成]
    [任务列表 QScrollArea + QVBoxLayout]
    [32px 状态栏: 总数 · 下载中 · 已完成 · 失败]
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
from app.models import TaskItem
from app.repositories import TaskItemRepository, TaskRepository
from ui.widgets.task_item_widget import TaskItemWidget
from worker.download_bridge import DownloadBridge

logger = get_logger(__name__)


class DownloadPage(QWidget):
    """下载任务页。

    信号:
        pause_all_clicked: 点击"全部暂停"按钮。
        resume_all_clicked: 点击"全部开始"按钮。
        clear_completed_clicked: 点击"清空已完成"按钮（确认后）。
        pause_item: 任务行发 pause_clicked，转发 task_item_id。
        resume_item: 任务行发 resume_clicked，转发 task_item_id。
        retry_item: 任务行发 retry_clicked，转发 task_item_id。
        navigate_to_fetch: 空状态点击"去添加链接"，请求切换到链接抓取页。
    """

    pause_all_clicked = Signal()
    resume_all_clicked = Signal()
    clear_completed_clicked = Signal()
    pause_item = Signal(int)
    resume_item = Signal(int)
    retry_item = Signal(int)
    navigate_to_fetch = Signal()

    def __init__(
        self,
        download_bridge: DownloadBridge,
        conn: sqlite3.Connection,
        parent: QWidget | None = None,
    ) -> None:
        """初始化下载任务页。

        Args:
            download_bridge: 下载引擎桥接器。
            conn: 数据库连接。
            parent: 父控件。
        """
        super().__init__(parent)
        self._bridge = download_bridge
        self._conn = conn
        self._task_repo = TaskRepository(conn)
        self._item_repo = TaskItemRepository(conn)
        self._item_widgets: dict[int, TaskItemWidget] = {}

        self._setup_ui()
        self._connect_bridge_signals()

    def _setup_ui(self) -> None:
        """构建页面布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题区
        title_label = QLabel("下载任务")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # 工具栏
        toolbar = QWidget()
        toolbar.setFixedHeight(48)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(24, 8, 24, 8)
        toolbar_layout.setSpacing(12)

        self._pause_all_btn = QPushButton("全部暂停")
        self._pause_all_btn.setToolTip("全部暂停 (Ctrl+P)")
        self._pause_all_btn.clicked.connect(self.pause_all_clicked.emit)
        toolbar_layout.addWidget(self._pause_all_btn)

        self._resume_all_btn = QPushButton("全部开始")
        self._resume_all_btn.setToolTip("全部开始 (Ctrl+S)")
        self._resume_all_btn.clicked.connect(self.resume_all_clicked.emit)
        toolbar_layout.addWidget(self._resume_all_btn)

        toolbar_layout.addStretch(1)

        self._clear_completed_btn = QPushButton("清空已完成")
        self._clear_completed_btn.setObjectName("dangerBtn")
        self._clear_completed_btn.clicked.connect(self._on_clear_completed)
        toolbar_layout.addWidget(self._clear_completed_btn)

        layout.addWidget(toolbar)

        # 任务列表区
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(24, 8, 24, 8)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch(1)
        self._scroll_area.setWidget(self._list_container)
        layout.addWidget(self._scroll_area, 1)

        # 空状态
        self._empty_widget = self._create_empty_widget()
        layout.addWidget(self._empty_widget)
        self._empty_widget.setVisible(False)

        # 状态栏
        self._status_label = QLabel("总数 0 · 下载中 0 · 已完成 0 · 失败 0")
        self._status_label.setObjectName("statusBarCounts")
        self._status_label.setFixedHeight(32)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._status_label.setContentsMargins(24, 0, 24, 0)
        layout.addWidget(self._status_label)

    def _create_empty_widget(self) -> QWidget:
        """创建空状态 widget。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon_label = QLabel("📥")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon_label)

        title = QLabel("还没有下载任务")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        desc = QLabel("前往链接抓取页添加链接")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #6B7280; font-size: 14px;")
        layout.addWidget(desc)

        go_btn = QPushButton("去添加链接")
        go_btn.setObjectName("primaryBtn")
        go_btn.setFixedWidth(120)
        go_btn.clicked.connect(self.navigate_to_fetch.emit)
        layout.addWidget(go_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return widget

    def _connect_bridge_signals(self) -> None:
        """连接 Bridge 的 WorkerSignals 到本页槽函数。"""
        signals = self._bridge._worker_signals  # noqa: SLF001
        signals.progress_updated.connect(self._on_progress_updated)
        signals.item_completed.connect(self._on_item_completed)
        signals.item_failed.connect(self._on_item_failed)

    def refresh(self) -> None:
        """从 DB 加载所有任务项，重建列表，更新状态栏。"""
        # 清空旧列表
        self._clear_list()

        # 从 DB 加载所有任务
        tasks = self._task_repo.get_pending_for_resume()
        for task in tasks:
            items = self._item_repo.get_by_task(task.id)  # type: ignore[arg-type]
            for item in items:
                self._add_item_widget(item)

        self._update_empty_state()
        self._update_status_bar()

    def _clear_list(self) -> None:
        """清空任务列表。"""
        for widget in self._item_widgets.values():
            widget.deleteLater()
        self._item_widgets.clear()

    def _add_item_widget(self, item: TaskItem) -> TaskItemWidget:
        """添加任务行到列表。

        Args:
            item: 任务项数据。

        Returns:
            创建的 TaskItemWidget。
        """
        widget = TaskItemWidget(item)
        # 连接信号
        widget.pause_clicked.connect(self.pause_item.emit)
        widget.resume_clicked.connect(self.resume_item.emit)
        widget.retry_clicked.connect(self.retry_item.emit)
        widget.open_file_clicked.connect(self._on_open_file)

        # 插入到 stretch 之前
        count = self._list_layout.count()
        self._list_layout.insertWidget(count - 1, widget)

        if item.id is not None:
            self._item_widgets[item.id] = widget
        return widget

    def _update_empty_state(self) -> None:
        """根据列表是否为空切换空状态显示。"""
        has_items = len(self._item_widgets) > 0
        self._empty_widget.setVisible(not has_items)
        self._scroll_area.setVisible(has_items)

    def _update_status_bar(self) -> None:
        """统计各状态数量，更新状态栏。"""
        total = len(self._item_widgets)
        downloading = 0
        completed = 0
        failed = 0
        for widget in self._item_widgets.values():
            status = widget._task_item.status  # noqa: SLF001
            if status == "downloading":
                downloading += 1
            elif status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
        self._status_label.setText(
            f"总数 {total} · 下载中 {downloading} · 已完成 {completed} · 失败 {failed}"
        )

    def _on_progress_updated(self, updates: list) -> None:
        """Bridge progress_updated 信号槽：批量更新进度。

        Args:
            updates: ProgressUpdate 列表。
        """
        for update in updates:
            task_item_id = update.task_item_id
            widget = self._item_widgets.get(task_item_id)
            if widget is not None:
                widget.update_progress(update.downloaded_bytes, update.total_bytes)

    def _on_item_completed(self, task_item_id: int) -> None:
        """Bridge item_completed 信号槽：标记完成。

        Args:
            task_item_id: 完成的任务项 ID。
        """
        widget = self._item_widgets.get(task_item_id)
        if widget is not None:
            widget.update_status("completed")
            self._update_status_bar()

    def _on_item_failed(self, task_item_id: int, reason: str) -> None:
        """Bridge item_failed 信号槽：标记失败。

        Args:
            task_item_id: 失败的任务项 ID。
            reason: 失败原因。
        """
        widget = self._item_widgets.get(task_item_id)
        if widget is not None:
            widget.update_status("failed", reason)
            self._update_status_bar()

    def _on_clear_completed(self) -> None:
        """清空已完成按钮点击：弹确认后发信号。"""
        completed_count = sum(
            1
            for w in self._item_widgets.values()
            if w._task_item.status == "completed"  # noqa: SLF001
        )
        if completed_count == 0:
            return

        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确认清空已完成任务？将永久删除 {completed_count} 条已完成任务，此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 移除已完成的 widget
            to_remove = [
                item_id
                for item_id, w in self._item_widgets.items()
                if w._task_item.status == "completed"  # noqa: SLF001
            ]
            for item_id in to_remove:
                widget = self._item_widgets.pop(item_id)
                widget.deleteLater()
            self.clear_completed_clicked.emit()
            self._update_empty_state()
            self._update_status_bar()

    def _on_open_file(self, path: str) -> None:
        """打开文件所在文件夹。

        Args:
            path: 本地文件路径。
        """
        from pathlib import Path

        folder = str(Path(path).parent) if path else ""
        if folder:
            QDesktopServices.openUrl(folder)
