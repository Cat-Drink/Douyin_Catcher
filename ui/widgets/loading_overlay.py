"""Loading 状态遮罩组件模块。

实现半透明遮罩组件，覆盖父组件区域，显示 loading 动画 + 文字 + 可选进度 + 取消按钮，
用于解析链接 / 测试 Cookie / 主页抓取等耗时操作反馈。

严格遵循设计文档 7.6 节操作反馈与 UI/UX 规范 6.2 节 Loading 状态设计。

使用方式::

    overlay = LoadingOverlay(parent)
    overlay.show(parent, "正在解析链接...", cancelable=True)
    overlay.update_progress(20, 100)
    overlay.hide()
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

# === 关键常量 ===
OVERLAY_BG_COLOR: str = "rgba(255, 255, 255, 0.7)"  # 浅色半透明背景
OVERLAY_ANIMATION_SIZE: int = 32  # 动画尺寸 32px
OVERLAY_ANIMATION_COLOR: str = "#7C3AED"  # 动画主色
OVERLAY_SPIN_INTERVAL_MS: int = 50  # 旋转动画刷新间隔


class _SpinnerWidget(QWidget):
    """自绘旋转圆圈 loading 动画。

    通过 QPropertyAnimation 旋转 angle 属性，paintEvent 绘制弧线。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化旋转动画控件。"""
        super().__init__(parent)
        self._angle: int = 0
        self._anim: QPropertyAnimation | None = None
        self.setFixedSize(OVERLAY_ANIMATION_SIZE, OVERLAY_ANIMATION_SIZE)

    def start(self) -> None:
        """启动旋转动画。"""
        if self._anim is not None:
            return
        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setDuration(1000)
        self._anim.setStartValue(0)
        self._anim.setEndValue(360)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.start()

    def stop(self) -> None:
        """停止旋转动画。"""
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        self._angle = 0
        self.update()

    def _get_angle(self) -> int:
        """获取当前角度。"""
        return self._angle

    def _set_angle(self, value: int) -> None:
        """设置当前角度并触发重绘。"""
        self._angle = value
        self.update()

    angle = property(_get_angle, _set_angle)

    def paintEvent(self, _event: QPaintEvent) -> None:
        """绘制旋转弧线。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        margin = 4
        rect = QRectF(margin, margin, width - 2 * margin, height - 2 * margin)

        # 背景圆环（淡色）
        bg_pen = QPen(QColor("#E5E7EB"))
        bg_pen.setWidth(3)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # 前景弧线（主色，旋转）
        fg_pen = QPen(QColor(OVERLAY_ANIMATION_COLOR))
        fg_pen.setWidth(3)
        painter.setPen(fg_pen)
        start_angle = int(self._angle * 16)
        span_angle = 90 * 16  # 90 度弧
        painter.drawArc(rect, -start_angle, span_angle)


class LoadingOverlay(QWidget):
    """半透明遮罩组件。

    覆盖父组件区域，显示 loading 动画 + 文字 + 可选进度 + 取消按钮。
    遮罩通过 ``raise_()`` 置于 parent 所有子控件之上，parent resize 时自动跟随。

    信号:
        cancel_clicked: 用户点击取消按钮。
    """

    cancel_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化遮罩。

        Args:
            parent: 父控件（可选，show 时可重新指定）。
        """
        super().__init__(parent)
        self._target_parent: QWidget | None = None
        self._spinner: _SpinnerWidget | None = None
        self._message_label: QLabel | None = None
        self._progress_label: QLabel | None = None
        self._cancel_btn: QPushButton | None = None
        self._resize_check_timer: QTimer | None = None
        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        """构建遮罩内部布局。"""
        # 遮罩透明背景，paintEvent 绘制半透明遮罩
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 旋转动画
        self._spinner = _SpinnerWidget(self)
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignCenter)

        # 提示文字
        self._message_label = QLabel()
        self._message_label.setStyleSheet(
            "color: #111827; font-size: 14px; background: transparent;"
        )
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._message_label)

        # 进度文字
        self._progress_label = QLabel()
        self._progress_label.setStyleSheet(
            "color: #6B7280; font-size: 12px; background: transparent;"
        )
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        # 取消按钮
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setVisible(False)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, _event: QPaintEvent) -> None:
        """绘制半透明遮罩背景。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 178))

    def show(
        self,
        parent: QWidget | None = None,
        message: str = "加载中...",
        cancelable: bool = True,
    ) -> None:
        """显示遮罩。

        设置 parent、覆盖 parent 区域、显示 message、cancelable 控制取消按钮显隐。

        Args:
            parent: 父控件，遮罩覆盖此控件区域。None 时使用构造时的 parent。
            message: 提示文字。
            cancelable: 是否显示取消按钮。
        """
        if parent is not None:
            self._target_parent = parent
            if self.parent() is not parent:
                self.setParent(parent)
        elif self._target_parent is None and self.parent() is not None:
            self._target_parent = self.parent()

        # 设置文字
        self._message_label.setText(message)
        self._progress_label.setVisible(False)
        self._progress_label.setText("")
        self._cancel_btn.setVisible(cancelable)

        # 调整大小并显示
        self._resize_to_parent()
        self.setVisible(True)
        self.raise_()

        # 启动旋转动画
        if self._spinner is not None:
            self._spinner.start()

        # 启动 resize 跟踪定时器
        if self._resize_check_timer is None:
            self._resize_check_timer = QTimer(self)
            self._resize_check_timer.setInterval(OVERLAY_SPIN_INTERVAL_MS)
            self._resize_check_timer.timeout.connect(self._resize_to_parent)
        self._resize_check_timer.start()

    def hide(self) -> None:
        """隐藏遮罩：停止动画、隐藏控件。"""
        if self._resize_check_timer is not None:
            self._resize_check_timer.stop()
        if self._spinner is not None:
            self._spinner.stop()
        super().hide()

    def update_message(self, message: str) -> None:
        """更新提示文字。

        Args:
            message: 新的提示文字。
        """
        if self._message_label is not None:
            self._message_label.setText(message)

    def update_progress(self, current: int, total: int) -> None:
        """更新进度显示。

        Args:
            current: 当前进度。
            total: 总数。total 为 0 时显示"已获取 N 条"。
        """
        if self._progress_label is None:
            return
        self._progress_label.setVisible(True)
        if total > 0:
            self._progress_label.setText(f"{current} / {total}")
        else:
            self._progress_label.setText(f"已获取 {current} 条")

    def _resize_to_parent(self) -> None:
        """遮罩大小跟随 parent 大小。"""
        if self._target_parent is None:
            return
        parent_size = self._target_parent.size()
        if parent_size.width() <= 0 or parent_size.height() <= 0:
            return
        if self.size() != parent_size:
            self.setGeometry(0, 0, parent_size.width(), parent_size.height())

    def _on_cancel_clicked(self) -> None:
        """取消按钮点击：发 cancel_clicked 信号。"""
        self.cancel_clicked.emit()
