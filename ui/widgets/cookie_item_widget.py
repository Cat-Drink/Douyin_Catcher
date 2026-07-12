"""Cookie 行组件模块。

实现单个 Cookie 列表行组件，包含状态指示灯、标签、状态文字、
最后使用时间、测试/删除按钮。

严格遵循 UIUX 规范 4.5.2 节与 4.6 节。

布局结构::

    [状态灯 8x8] [标签] [状态文字] [最后使用时间] [测试按钮] [删除按钮]
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.logger import get_logger
from app.models import Cookie

logger = get_logger(__name__)

# 状态映射: status → (状态灯颜色, 状态文字)
_STATUS_MAP: dict[str, tuple[str, str]] = {
    "valid": ("#10B981", "有效"),
    "invalid": ("#EF4444", "失效"),
    "untested": ("#F59E0B", "未测试"),
}


class CookieItemWidget(QWidget):
    """单个 Cookie 列表行组件。

    信号:
        test_clicked: 点击"测试"按钮，传 cookie_id。
        delete_clicked: 点击"删除"按钮，传 cookie_id。
    """

    test_clicked = Signal(int)
    delete_clicked = Signal(int)

    def __init__(self, cookie: Cookie, parent: QWidget | None = None) -> None:
        """初始化 Cookie 行。

        Args:
            cookie: Cookie 数据。
            parent: 父控件。
        """
        super().__init__(parent)
        self._cookie = cookie
        self._setup_ui()
        self.update_from_cookie(cookie)

    def _setup_ui(self) -> None:
        """构建行布局。"""
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        # 状态指示灯
        self._status_dot = QLabel()
        self._status_dot.setObjectName("statusDot")
        self._status_dot.setFixedSize(8, 8)
        layout.addWidget(self._status_dot)

        # 标签
        self._label_label = QLabel()
        self._label_label.setObjectName("cookieLabel")
        self._label_label.setMinimumWidth(80)
        layout.addWidget(self._label_label)

        # 状态文字
        self._status_text = QLabel()
        self._status_text.setObjectName("cookieStatus")
        self._status_text.setMinimumWidth(120)
        layout.addWidget(self._status_text)

        # 最后使用时间
        self._last_used_label = QLabel()
        self._last_used_label.setObjectName("cookieLastUsed")
        layout.addWidget(self._last_used_label, 1)

        # 测试按钮
        self._test_btn = QPushButton("测试")
        self._test_btn.setFixedHeight(28)
        self._test_btn.clicked.connect(self._on_test_clicked)
        layout.addWidget(self._test_btn)

        # 删除按钮
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setFixedHeight(28)
        self._delete_btn.setStyleSheet(
            "QPushButton { color: #EF4444; border: none; }"
            "QPushButton:hover { background-color: #FEE2E2; border-radius: 4px; }"
        )
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self._delete_btn)

    def update_from_cookie(self, cookie: Cookie) -> None:
        """根据 Cookie 数据更新显示。

        Args:
            cookie: Cookie 数据。
        """
        self._cookie = cookie

        # 标签
        self._label_label.setText(cookie.label or f"Cookie #{cookie.id}")

        # 状态灯与文字
        self._apply_status(cookie.status)

        # 最后使用时间
        if cookie.last_used:
            self._last_used_label.setText(f"最后使用：{cookie.last_used}")
        else:
            self._last_used_label.setText("未使用过")

    def _apply_status(self, status: str) -> None:
        """应用状态灯颜色与状态文字。

        Args:
            status: Cookie 状态 (valid/invalid/untested)。
        """
        color, text = _STATUS_MAP.get(status, ("#F59E0B", "未测试"))
        self._status_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        self._status_text.setText(text)

    def set_testing(self) -> None:
        """设置为测试中状态：状态灯黄闪，测试按钮禁用。"""
        self._status_dot.setStyleSheet("background-color: #F59E0B; border-radius: 4px;")
        self._status_text.setText("测试中...")
        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")

    def set_test_result(self, is_valid: bool, message: str) -> None:
        """设置测试结果。

        Args:
            is_valid: Cookie 是否有效。
            message: 结果消息（无效时为失败原因）。
        """
        self._test_btn.setEnabled(True)
        self._test_btn.setText("测试")
        if is_valid:
            self._cookie.status = "valid"
            self._apply_status("valid")
        else:
            self._cookie.status = "invalid"
            self._apply_status("invalid")
            self._status_text.setText(f"失效（{message}）")

    def _on_test_clicked(self) -> None:
        """测试按钮点击。"""
        if self._cookie.id is not None:
            self.test_clicked.emit(self._cookie.id)

    def _on_delete_clicked(self) -> None:
        """删除按钮点击。"""
        if self._cookie.id is not None:
            self.delete_clicked.emit(self._cookie.id)
