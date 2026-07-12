"""Toast 轻量提示组件模块。

实现自动消失、不阻塞 UI 的轻量提示组件，用于操作成功 / 信息 / 警告反馈。

严格遵循 UI/UX 规范 4.11 节 Toast 提示：
    - 位置：窗口底部居中，距底部 24px
    - 高度 40px，内边距 12px 16px，圆角 4px
    - 背景 #111827（深色），文字 #FFFFFF
    - 显示时长 2.5 秒
    - 动画：从底部滑入（200ms ease-out），淡出（200ms）

使用方式::

    Toast.show_success(parent, "设置已保存")
    Toast.show_info(parent, "已加入下载队列")
    Toast.show_warning(parent, "Cookie 未配置，部分功能不可用")
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

# === 关键常量（UI/UX 规范 4.11 节） ===
TOAST_DURATION_MS: int = 2500  # 显示时长 2.5 秒
TOAST_HEIGHT: int = 40  # 高度 40px
TOAST_MARGIN_BOTTOM: int = 24  # 距底部 24px
TOAST_BG_COLOR: str = "#111827"  # 深色背景
TOAST_TEXT_COLOR: str = "#FFFFFF"  # 白色文字
ANIM_DURATION_MS: int = 200  # 滑入/淡出动画时长 200ms

# Toast 类型 → 图标 Unicode 字符 + 图标颜色
_TOAST_TYPE_MAP: dict[str, tuple[str, str]] = {
    "info": ("ℹ", "#3B82F6"),  # Info-Blue
    "success": ("✓", "#10B981"),  # Success-Green
    "warning": ("⚠", "#F59E0B"),  # Warning-Yellow
}


class Toast(QFrame):
    """轻量提示组件。

    自动消失、不阻塞 UI、不抢焦点，用于操作成功 / 信息 / 警告反馈。
    同一 parent 同时只显示一个 Toast（新 Toast 显示前隐藏旧 Toast）。

    推荐使用静态便捷方法 ``show_info`` / ``show_success`` / ``show_warning``，
    也可实例化后调用 ``_show`` 方法。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化 Toast。

        Args:
            parent: 父控件，Toast 将定位在 parent 底部居中。
        """
        super().__init__(parent)
        self._hide_anim: QPropertyAnimation | None = None
        self._slide_anim: QPropertyAnimation | None = None
        self._timer: QTimer | None = None
        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        """构建 Toast 内部布局与样式。"""
        self.setFixedHeight(TOAST_HEIGHT)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"Toast {{ background-color: {TOAST_BG_COLOR};" f" border-radius: 4px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 图标
        self._icon_label = QLabel()
        font = QFont()
        font.setPointSize(12)
        self._icon_label.setFont(font)
        self._icon_label.setStyleSheet(
            f"color: {TOAST_TEXT_COLOR}; background: transparent; border: none;"
        )
        layout.addWidget(self._icon_label)

        # 文字
        self._text_label = QLabel()
        self._text_label.setStyleSheet(
            f"color: {TOAST_TEXT_COLOR}; background: transparent; border: none;"
            f" font-size: 14px;"
        )
        layout.addWidget(self._text_label)

    def _show(self, toast_type: str, parent: QWidget, message: str) -> None:
        """显示 Toast。

        设置图标、文字、定位到 parent 底部居中，播放滑入动画，启动自动消失定时器。
        同一 parent 同时只显示一个 Toast：先隐藏已有 Toast。

        Args:
            toast_type: Toast 类型，"info" / "success" / "warning"。
            parent: 父控件，Toast 定位基准。
            message: 提示文字。
        """
        # 设置 parent（若与当前 parent 不同则重新设置）
        if self.parent() is not parent:
            self.setParent(parent)

        # 隐藏同 parent 的旧 Toast（单例管理）
        if parent is not None:
            for child in parent.children():
                if isinstance(child, Toast) and child is not self and child.isVisible():
                    child._hide_immediately()

        # 设置图标与颜色
        icon_char, icon_color = _TOAST_TYPE_MAP.get(toast_type, ("ℹ", "#3B82F6"))
        self._icon_label.setText(icon_char)
        self._icon_label.setStyleSheet(
            f"color: {icon_color}; background: transparent; border: none;"
            f" font-size: 16px; font-weight: bold;"
        )
        self._text_label.setText(message)

        # 调整尺寸并定位
        self.adjustSize()
        self._position_at_bottom(parent)

        # 显示并播放滑入动画
        self.show()
        self.raise_()
        self._play_slide_in(parent)

        # 启动自动消失定时器
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._hide_with_animation)
        self._timer.start(TOAST_DURATION_MS)

    def _position_at_bottom(self, parent: QWidget) -> None:
        """计算并设置 Toast 在 parent 底部居中位置（距底部 24px）。

        Args:
            parent: 父控件，作为定位基准。
        """
        if parent is None:
            return
        parent_width = parent.width()
        toast_width = self.width()
        x = (parent_width - toast_width) // 2
        y = parent.height() - TOAST_HEIGHT - TOAST_MARGIN_BOTTOM
        self.move(x, max(0, y))

    def _play_slide_in(self, parent: QWidget) -> None:
        """播放从底部滑入动画（200ms ease-out）。

        Args:
            parent: 父控件，用于计算起始 Y 坐标。
        """
        if parent is None:
            return
        start_y = parent.height() - TOAST_MARGIN_BOTTOM
        end_y = parent.height() - TOAST_HEIGHT - TOAST_MARGIN_BOTTOM
        x = self.x()

        self._slide_anim = QPropertyAnimation(self, b"pos", self)
        self._slide_anim.setDuration(ANIM_DURATION_MS)
        self._slide_anim.setStartValue((x, start_y))
        self._slide_anim.setEndValue((x, max(0, end_y)))
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.start()

    def _hide_with_animation(self) -> None:
        """淡出动画后隐藏。"""
        self._hide_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._hide_anim.setDuration(ANIM_DURATION_MS)
        self._hide_anim.setStartValue(1.0)
        self._hide_anim.setEndValue(0.0)
        self._hide_anim.finished.connect(self._hide_immediately)
        self._hide_anim.start()

    def _hide_immediately(self) -> None:
        """立即隐藏 Toast（停止动画与定时器）。"""
        if self._slide_anim is not None:
            self._slide_anim.stop()
        if self._hide_anim is not None:
            self._hide_anim.stop()
        if self._timer is not None:
            self._timer.stop()
        self.setWindowOpacity(1.0)
        self.hide()

    @staticmethod
    def show_info(parent: QWidget, message: str) -> Toast:
        """显示信息提示（Info-Blue 图标）。

        Args:
            parent: 父控件，Toast 定位基准。
            message: 提示文字。

        Returns:
            创建的 Toast 实例。
        """
        toast = Toast(parent)
        toast._show("info", parent, message)  # noqa: SLF001
        return toast

    @staticmethod
    def show_success(parent: QWidget, message: str) -> Toast:
        """显示成功提示（Success-Green 图标）。

        Args:
            parent: 父控件，Toast 定位基准。
            message: 提示文字。

        Returns:
            创建的 Toast 实例。
        """
        toast = Toast(parent)
        toast._show("success", parent, message)  # noqa: SLF001
        return toast

    @staticmethod
    def show_warning(parent: QWidget, message: str) -> Toast:
        """显示警告提示（Warning-Yellow 图标）。

        Args:
            parent: 父控件，Toast 定位基准。
            message: 提示文字。

        Returns:
            创建的 Toast 实例。
        """
        toast = Toast(parent)
        toast._show("warning", parent, message)  # noqa: SLF001
        return toast
