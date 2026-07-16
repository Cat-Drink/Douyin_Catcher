"""Cookie 配置页模块。

实现 Cookie 配置页，包含操作栏、Cookie 列表、添加 Cookie 弹窗、
教程折叠面板、状态栏。

严格遵循设计文档 3.1 节页面 3、7.5 节教程内容与 UIUX 规范 5.4 节。

布局结构::

    [56px 标题区: "Cookie 配置"]
    [48px 操作栏: + 添加 Cookie / 全部测试 / 教程 ▼]
    [Cookie 列表 QScrollArea]
    [折叠面板: Cookie 获取教程（7步）]
    [状态栏: 共 N · 有效 N · 失效 N · 未测试 N]
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
from app.models import Cookie
from app.repositories import CookieRepository
from ui.widgets.cookie_item_widget import CookieItemWidget
from ui.widgets.toast import Toast
from worker.crawler_bridge import CrawlerBridge

logger = get_logger(__name__)

# 教程步骤数据
_TUTORIAL_STEPS: list[tuple[str, str]] = [
    ("1. 打开抖音网页版", "浏览器访问 https://www.douyin.com 并登录"),
    ("2. 打开开发者工具", "按 F12，切到 Network 标签"),
    ("3. 刷新页面", "按 F5，让请求列表出现"),
    ("4. 找到任意请求", "点任意一条 douyin.com 请求"),
    ("5. 复制 Cookie", "Request Headers 里 Cookie 字段，右键复制"),
    ("6. 粘贴到左侧", "粘到添加 Cookie 弹窗"),
    ('7. 点"测试 Cookie"', "验证是否有效"),
]

# 教程截图目录与显示宽度
_TUTORIAL_DIR = Path(__file__).parent.parent / "assets" / "cookie_tutorial"
_TUTORIAL_IMAGE_WIDTH = 400


class AddCookieDialog(QDialog):
    """添加 Cookie 弹窗。

    模态对话框，宽 480px，含标签输入、Cookie 内容多行文本、错误提示。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化弹窗。"""
        super().__init__(parent)
        self.setWindowTitle("添加 Cookie")
        self.setFixedWidth(480)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建弹窗布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("添加 Cookie")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        desc = QLabel("从浏览器开发者工具复制 Cookie 字段粘贴到下方")
        desc.setObjectName("dialogDesc")
        layout.addWidget(desc)

        # 标签输入
        label_label = QLabel("标签（可选）")
        label_label.setObjectName("fieldLabel")
        layout.addWidget(label_label)
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("如：账号A")
        layout.addWidget(self._label_edit)

        # Cookie 内容
        content_label = QLabel("Cookie 内容")
        content_label.setObjectName("fieldLabel")
        layout.addWidget(content_label)
        self._content_edit = QPlainTextEdit()
        self._content_edit.setFixedHeight(120)
        self._content_edit.setPlaceholderText("粘贴 Cookie 字符串...")
        layout.addWidget(self._content_edit)

        # 错误提示
        self._error_label = QLabel()
        self._error_label.setObjectName("errorText")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("测试并保存")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def get_content(self) -> str:
        """返回 Cookie 内容文本。"""
        return self._content_edit.toPlainText().strip()

    def get_label(self) -> str:
        """返回标签文本。"""
        return self._label_edit.text().strip()

    def show_error(self, message: str) -> None:
        """显示错误提示。"""
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _on_save(self) -> None:
        """保存按钮点击：校验非空后 accept。"""
        if not self.get_content():
            self.show_error("请输入 Cookie 内容")
            return
        self.accept()


class CookiePage(QWidget):
    """Cookie 配置页。

    信号:
        add_cookie_requested: 添加 Cookie 弹窗确认，传 content 与 label。
        remove_cookie_requested: Cookie 行删除确认后，传 cookie_id。
        test_cookie_requested: Cookie 行点击"测试"，传 cookie_id。
        test_all_cookies_requested: 点击"全部测试"。
    """

    add_cookie_requested = Signal(str, str)
    remove_cookie_requested = Signal(int)
    test_cookie_requested = Signal(int)
    test_all_cookies_requested = Signal()

    def __init__(
        self,
        crawler_bridge: CrawlerBridge,
        conn: sqlite3.Connection,
        parent: QWidget | None = None,
    ) -> None:
        """初始化 Cookie 配置页。

        Args:
            crawler_bridge: 爬虫层桥接器。
            conn: 数据库连接。
            parent: 父控件。
        """
        super().__init__(parent)
        self._bridge = crawler_bridge
        self._conn = conn
        self._cookie_repo = CookieRepository(conn)
        self._cookie_widgets: dict[int, CookieItemWidget] = {}

        self._setup_ui()
        self._connect_bridge_signals()

    def _setup_ui(self) -> None:
        """构建页面布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题区
        title_label = QLabel("Cookie 配置")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # 操作栏
        toolbar = QWidget()
        toolbar.setFixedHeight(48)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(24, 8, 24, 8)
        toolbar_layout.setSpacing(12)

        add_btn = QPushButton("+ 添加 Cookie")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._on_add_cookie)
        toolbar_layout.addWidget(add_btn)

        test_all_btn = QPushButton("全部测试")
        test_all_btn.clicked.connect(self.test_all_cookies_requested.emit)
        toolbar_layout.addWidget(test_all_btn)

        toolbar_layout.addStretch(1)

        self._tutorial_btn = QPushButton("教程 ▼")
        self._tutorial_btn.setObjectName("textBtn")
        self._tutorial_btn.clicked.connect(self._toggle_tutorial)
        toolbar_layout.addWidget(self._tutorial_btn)

        layout.addWidget(toolbar)

        # Cookie 列表区
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

        # 教程折叠面板
        self._tutorial_container = self._create_tutorial_widget()
        self._tutorial_container.setVisible(False)
        layout.addWidget(self._tutorial_container)

        # 状态栏
        self._status_label = QLabel("共 0 · 有效 0 · 失效 0 · 未测试 0")
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

        icon_label = QLabel("🍪")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon_label)

        title = QLabel("还没有配置 Cookie")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        desc = QLabel("配置 Cookie 后才能下载视频")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #6B7280; font-size: 14px;")
        layout.addWidget(desc)

        add_btn = QPushButton("+ 添加 Cookie")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedWidth(140)
        add_btn.clicked.connect(self._on_add_cookie)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        tutorial_btn = QPushButton("查看教程")
        tutorial_btn.setObjectName("textBtn")
        tutorial_btn.clicked.connect(self._toggle_tutorial)
        layout.addWidget(tutorial_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return widget

    def _create_tutorial_widget(self) -> QWidget:
        """创建教程折叠面板。"""
        widget = QWidget()
        widget.setStyleSheet("background-color: #F9FAFB; border-top: 1px solid #E5E7EB;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)

        title = QLabel("Cookie 获取教程")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        for idx, (step_title, step_desc) in enumerate(_TUTORIAL_STEPS, start=1):
            step_layout = QVBoxLayout()
            step_layout.setSpacing(4)
            step_title_label = QLabel(step_title)
            step_title_label.setStyleSheet("font-size: 14px; font-weight: 500;")
            step_layout.addWidget(step_title_label)
            step_desc_label = QLabel(step_desc)
            step_desc_label.setStyleSheet("color: #6B7280; font-size: 13px;")
            step_layout.addWidget(step_desc_label)
            # 截图 QLabel：加载 stepN.png，缺失或加载失败时显示占位框
            image_label = QLabel()
            image_path = _TUTORIAL_DIR / f"step{idx}.png"
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                image_label.setPixmap(
                    pixmap.scaledToWidth(
                        _TUTORIAL_IMAGE_WIDTH,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                image_label.setText(f"📷 截图待提供：step{idx}.png")
                image_label.setFixedHeight(120)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                image_label.setStyleSheet(
                    "border: 1px dashed #D1D5DB; border-radius: 8px; "
                    "color: #9CA3AF; background-color: #FAFAFA; "
                    "font-size: 13px;"
                )
            step_layout.addWidget(image_label)
            layout.addLayout(step_layout)

        return widget

    def _connect_bridge_signals(self) -> None:
        """连接 Bridge 的 WorkerSignals。"""
        signals = self._bridge._worker_signals  # noqa: SLF001
        signals.cookie_test_result.connect(self._on_cookie_test_result)

    def refresh(self) -> None:
        """从 DB 加载全部 Cookie，重建列表，更新状态栏。"""
        self._clear_list()
        cookies = self._cookie_repo.get_all()
        for cookie in cookies:
            self._add_cookie_widget(cookie)
        self._update_empty_state()
        self._update_status_bar()

    def _clear_list(self) -> None:
        """清空 Cookie 列表。"""
        for widget in self._cookie_widgets.values():
            widget.deleteLater()
        self._cookie_widgets.clear()

    def _add_cookie_widget(self, cookie: Cookie) -> CookieItemWidget:
        """添加 Cookie 行到列表。"""
        widget = CookieItemWidget(cookie)
        widget.test_clicked.connect(self.test_cookie_requested.emit)
        widget.delete_clicked.connect(self._on_delete_cookie)
        count = self._list_layout.count()
        self._list_layout.insertWidget(count - 1, widget)
        if cookie.id is not None:
            self._cookie_widgets[cookie.id] = widget
        return widget

    def _update_empty_state(self) -> None:
        """切换空状态显示。"""
        has_items = len(self._cookie_widgets) > 0
        self._empty_widget.setVisible(not has_items)
        self._scroll_area.setVisible(has_items)

    def _update_status_bar(self) -> None:
        """更新状态栏计数。"""
        total = len(self._cookie_widgets)
        valid = sum(
            1 for w in self._cookie_widgets.values() if w._cookie.status == "valid"
        )  # noqa: SLF001
        invalid = sum(
            1 for w in self._cookie_widgets.values() if w._cookie.status == "invalid"
        )  # noqa: SLF001
        untested = sum(
            1 for w in self._cookie_widgets.values() if w._cookie.status == "untested"
        )  # noqa: SLF001
        self._status_label.setText(
            f"共 {total} · 有效 {valid} · 失效 {invalid} · 未测试 {untested}"
        )

    def _on_add_cookie(self) -> None:
        """添加 Cookie 按钮点击。"""
        dialog = AddCookieDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            content = dialog.get_content()
            label = dialog.get_label()
            self.add_cookie_requested.emit(content, label)

    def _on_delete_cookie(self, cookie_id: int) -> None:
        """删除 Cookie 确认。"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确认删除此 Cookie？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.remove_cookie_requested.emit(cookie_id)

    def _on_cookie_test_result(self, cookie_id: int, is_valid: bool, message: str) -> None:
        """Bridge cookie_test_result 信号槽。"""
        widget = self._cookie_widgets.get(cookie_id)
        if widget is not None:
            widget.set_test_result(is_valid, message)
            self._update_status_bar()
        # Toast 反馈测试结果
        if is_valid:
            Toast.show_success(self, "Cookie 测试通过")
        else:
            Toast.show_warning(self, f"Cookie 测试失败：{message}")

    def set_cookie_testing(self, cookie_id: int) -> None:
        """设置某 Cookie 为测试中状态。

        Args:
            cookie_id: Cookie ID。
        """
        widget = self._cookie_widgets.get(cookie_id)
        if widget is not None:
            widget.set_testing()

    def _toggle_tutorial(self) -> None:
        """切换教程折叠面板显示。"""
        visible = self._tutorial_container.isVisible()
        self._tutorial_container.setVisible(not visible)
        self._tutorial_btn.setText("教程 ▲" if not visible else "教程 ▼")
