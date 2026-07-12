"""统一错误处理系统模块。

实现 ``ErrorHandler`` 类，覆盖设计文档 7.2 节定义的 8 类错误，
每类错误提供"人话解释 + 下一步建议"，并按错误类型分发到
任务行级 / 全局弹窗 / 输入框下方三种展示位置。

严格遵循设计文档第 7 节（错误处理与用户体验）核心原则：
    绝不让用户看到原始异常栈，每个错误都要有人话解释 + 下一步建议。

错误类型与展示位置::

    cookie_invalid   → 全局弹窗 → "去配置 Cookie" → 跳转 Cookie 页
    network_error    → 任务行级 → 重试按钮
    video_not_found  → 任务行级 → 跳过
    verify_required  → 任务行级 → 稍后重试
    download_failed  → 任务行级 → 重新下载
    disk_full        → 全局弹窗 → "更换目录" → 跳转设置页
    invalid_link     → 输入框下方
    unknown_error    → 全局弹窗 → "复制详情"
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.logger import get_logger

if TYPE_CHECKING:
    from ui.main_window import MainWindow

logger = get_logger(__name__)


@dataclass(frozen=True)
class ErrorInfo:
    """错误信息映射条目。

    Attributes:
        title: 错误标题（全局弹窗用）。
        user_message: 人话解释（用户看到的）。
        action_text: 操作按钮文字（"下一步建议"的触发按钮）。
        action_type: 操作回调类型
            ("goto_cookie"/"goto_settings"/"redownload"/"copy_details"/"none")。
        display_position: 展示位置
            ("task_row"/"global"/"input"/"global_with_details")。
        severity: 严重程度 ("error"/"warning"/"info")，影响图标。
    """

    title: str
    user_message: str
    action_text: str
    action_type: str
    display_position: str
    severity: str


# === 错误信息映射表（完整 8 类，设计文档 7.2 节） ===
ERROR_MAPPING: dict[str, ErrorInfo] = {
    "cookie_invalid": ErrorInfo(
        title="Cookie 已失效",
        user_message="Cookie 已失效，抖音需要重新登录验证。请按教程重新获取 Cookie。",
        action_text="去配置 Cookie",
        action_type="goto_cookie",
        display_position="global",
        severity="error",
    ),
    "network_error": ErrorInfo(
        title="网络连接失败",
        user_message='网络连接失败，请检查网络后点"重试"。',
        action_text="重试",
        action_type="redownload",
        display_position="task_row",
        severity="error",
    ),
    "video_not_found": ErrorInfo(
        title="作品不可用",
        user_message="该作品已被删除或设为私密，无法下载。",
        action_text="跳过",
        action_type="none",
        display_position="task_row",
        severity="warning",
    ),
    "verify_required": ErrorInfo(
        title="触发安全验证",
        user_message="抖音要求安全验证，暂时无法下载此作品。请稍后重试，或更新 Cookie。",
        action_text="稍后重试",
        action_type="none",
        display_position="task_row",
        severity="error",
    ),
    "download_failed": ErrorInfo(
        title="下载失败",
        user_message="下载失败：{reason}（已重试 3 次）。检查原因后可手动重新下载。",
        action_text="重新下载",
        action_type="redownload",
        display_position="task_row",
        severity="error",
    ),
    "disk_full": ErrorInfo(
        title="磁盘空间不足",
        user_message="磁盘空间不足，无法保存到 {directory}。请更换下载目录或清理磁盘。",
        action_text="更换目录",
        action_type="goto_settings",
        display_position="global",
        severity="error",
    ),
    "invalid_link": ErrorInfo(
        title="链接格式错误",
        user_message="无法识别该链接，请确认是抖音视频/主页链接。",
        action_text="",
        action_type="none",
        display_position="input",
        severity="error",
    ),
    "unknown_error": ErrorInfo(
        title="发生未知错误",
        user_message='发生未知错误：{details}。可点"复制详情"反馈给开发者。',
        action_text="复制详情",
        action_type="copy_details",
        display_position="global_with_details",
        severity="error",
    ),
}


class _ErrorDialog(QDialog):
    """全局错误弹窗对话框。

    模态对话框，按 UI/UX 规范 4.8.2 节错误弹窗规格实现：
    宽度 440px、内边距 24px、圆角 12px、含图标/标题/描述/操作按钮区。
    """

    def __init__(
        self,
        title: str,
        message: str,
        action_text: str,
        action_callback: Callable[[], None],
        severity: str = "error",
        show_copy_details: bool = False,
        details: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """初始化错误弹窗。

        Args:
            title: 错误标题。
            message: 错误描述文字。
            action_text: 主操作按钮文字。
            action_callback: 主操作按钮回调。
            severity: 严重程度 ("error"/"warning"/"info")。
            show_copy_details: 是否显示"复制详情"按钮。
            details: 错误详情（复制到剪贴板）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._action_callback = action_callback
        self._details = details

        self.setWindowTitle(title)
        self.setFixedWidth(440)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._setup_ui(title, message, action_text, severity, show_copy_details)

    def _setup_ui(
        self,
        title: str,
        message: str,
        action_text: str,
        severity: str,
        show_copy_details: bool,
    ) -> None:
        """构建弹窗布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 图标 + 标题行
        icon_char = {"error": "✖", "warning": "⚠", "info": "ℹ"}.get(severity, "✖")
        icon_color = {"error": "#EF4444", "warning": "#F59E0B", "info": "#3B82F6"}.get(
            severity, "#EF4444"
        )
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        icon_label = QLabel(icon_char)
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            f"background-color: {icon_color}; color: #FFFFFF;"
            f" border-radius: 16px; font-size: 16px; font-weight: bold;"
        )
        header_layout.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        header_layout.addWidget(title_label, 1)
        layout.addLayout(header_layout)

        # 描述文字
        message_label = QLabel(message)
        message_label.setStyleSheet("color: #6B7280; font-size: 14px;")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        if show_copy_details:
            copy_btn = QPushButton("复制详情")
            copy_btn.clicked.connect(self._on_copy_details)
            btn_layout.addWidget(copy_btn)

        if action_text:
            action_btn = QPushButton(action_text)
            action_btn.setObjectName("primaryBtn")
            action_btn.clicked.connect(self._on_action)
            btn_layout.addWidget(action_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _on_action(self) -> None:
        """主操作按钮点击：执行回调后关闭。"""
        try:
            self._action_callback()
        except Exception:
            logger.exception("错误弹窗操作回调执行失败")
        self.accept()

    def _on_copy_details(self) -> None:
        """复制详情按钮点击：复制到剪贴板。"""
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and self._details:
            clipboard.setText(self._details)
        logger.debug("错误详情已复制到剪贴板")


class ErrorHandler(QObject):
    """统一错误处理入口。

    根据 error_type 分发到对应展示位置（任务行 / 全局弹窗 / 输入框），
    提供人话解释与下一步建议。

    信号:
        task_error_shown: 任务行级错误已展示，参数为 task_item_id 与消息。
        global_error_shown: 全局弹窗已展示，参数为标题。
        input_error_shown: 输入错误已展示，参数为消息。
    """

    task_error_shown = Signal(int, str)
    global_error_shown = Signal(str)
    input_error_shown = Signal(str)

    def __init__(
        self,
        main_window: MainWindow,
        parent: QObject | None = None,
    ) -> None:
        """初始化错误处理器。

        Args:
            main_window: 主窗口实例，用于页面跳转与查找页面控件。
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._main_window = main_window

    def handle_error(self, error_type: str, context: dict) -> None:
        """统一错误处理入口。

        查映射表获取人话提示 + 操作建议，按 error_type 分发到对应展示方法。

        Args:
            error_type: 错误类型字符串，取值见 ERROR_MAPPING 的 key。
            context: 错误上下文，含以下可选键：
                - task_item_id: 任务项 ID（任务行级错误必需）
                - input_widget: 输入框控件（输入错误必需）
                - details: 错误详情（未知错误用于复制）
                - directory: 磁盘空间不足时的目录路径
                - reason: 下载失败的具体原因
        """
        info = self._get_error_info(error_type)
        if info is None:
            logger.warning("未知错误类型: %s，按 unknown_error 处理", error_type)
            info = ERROR_MAPPING["unknown_error"]

        # 填充占位符
        user_message = self._fill_placeholders(info.user_message, context)

        if info.display_position == "task_row":
            task_item_id = context.get("task_item_id", 0)
            self.show_task_error(task_item_id, user_message)
        elif info.display_position in ("global", "global_with_details"):
            self.show_global_error(
                title=info.title,
                message=user_message,
                action_text=info.action_text,
                action_callback=self._make_action_callback(info.action_type, context),
                severity=info.severity,
                show_copy_details=info.display_position == "global_with_details",
                details=context.get("details", ""),
            )
        elif info.display_position == "input":
            input_widget = context.get("input_widget")
            if isinstance(input_widget, QWidget):
                self.show_input_error(input_widget, user_message)
            else:
                logger.warning("input 错误类型缺少 input_widget 参数")

    def show_task_error(self, task_item_id: int, message: str) -> None:
        """任务行级错误：在指定任务行下方显示红色小字，不打断其他任务。

        Args:
            task_item_id: 任务项 ID。
            message: 错误消息。
        """
        download_page = self._main_window._pages.get("download")  # noqa: SLF001
        if download_page is None:
            logger.warning("找不到下载页，无法显示任务行级错误")
            return
        item_widgets = getattr(download_page, "_item_widgets", {})
        widget = item_widgets.get(task_item_id)
        if widget is not None:
            widget.update_status("failed", message)
        else:
            logger.warning("找不到 task_item_id=%s 的任务行", task_item_id)
        self.task_error_shown.emit(task_item_id, message)

    def show_global_error(
        self,
        title: str,
        message: str,
        action_text: str,
        action_callback: Callable[[], None],
        severity: str = "error",
        show_copy_details: bool = False,
        details: str = "",
    ) -> None:
        """全局弹窗：弹模态对话框，含标题、说明、操作按钮。

        Args:
            title: 错误标题。
            message: 错误描述。
            action_text: 操作按钮文字（空字符串则不显示）。
            action_callback: 操作按钮回调。
            severity: 严重程度。
            show_copy_details: 是否显示"复制详情"按钮。
            details: 错误详情（复制到剪贴板）。
        """
        dialog = _ErrorDialog(
            title=title,
            message=message,
            action_text=action_text,
            action_callback=action_callback,
            severity=severity,
            show_copy_details=show_copy_details,
            details=details,
            parent=self._main_window,
        )
        dialog.exec()
        self.global_error_shown.emit(title)

    def show_input_error(self, input_widget: QWidget, message: str) -> None:
        """输入错误：在 input_widget 下方显示红色小字，输入框应用红色边框。

        Args:
            input_widget: 输入框控件。
            message: 错误消息。
        """
        input_widget.setProperty("error", True)
        input_widget.style().unpolish(input_widget)
        input_widget.style().polish(input_widget)

        # 查找或创建错误提示 QLabel
        parent = input_widget.parentWidget()
        if parent is None:
            return
        error_label: QLabel | None = getattr(input_widget, "_error_label", None)
        if error_label is None:
            error_label = QLabel(message)
            error_label.setStyleSheet("color: #EF4444; font-size: 12px;")
            error_label.setObjectName("inputErrorLabel")
            # 插入到 input_widget 之后
            parent_layout = parent.layout()
            if parent_layout is not None:
                index = parent_layout.indexOf(input_widget)
                parent_layout.insertWidget(index + 1, error_label)
            input_widget._error_label = error_label  # type: ignore[attr-defined]
        else:
            error_label.setText(message)
            error_label.setVisible(True)
        self.input_error_shown.emit(message)

    def clear_input_error(self, input_widget: QWidget) -> None:
        """清除输入错误：移除红色边框与提示文字。

        Args:
            input_widget: 输入框控件。
        """
        input_widget.setProperty("error", False)
        input_widget.style().unpolish(input_widget)
        input_widget.style().polish(input_widget)
        error_label = getattr(input_widget, "_error_label", None)
        if error_label is not None:
            error_label.setVisible(False)

    def _get_error_info(self, error_type: str) -> ErrorInfo | None:
        """查错误信息映射表，返回 ErrorInfo。

        Args:
            error_type: 错误类型字符串。

        Returns:
            ErrorInfo 实例，未找到返回 None。
        """
        return ERROR_MAPPING.get(error_type)

    def _fill_placeholders(self, template: str, context: dict) -> str:
        """填充 user_message 中的占位符。

        Args:
            template: 含占位符的模板字符串。
            context: 错误上下文。

        Returns:
            填充后的字符串。
        """
        reason = context.get("reason", "未知原因")
        directory = context.get("directory", "下载目录")
        details = context.get("details", "")
        # 简短描述：取异常类名 + 消息前 100 字符
        short_desc = details.split("\n", 1)[0][:100] if details else "未知错误"
        return template.format(reason=reason, directory=directory, details=short_desc)

    def _make_action_callback(self, action_type: str, context: dict) -> Callable[[], None]:
        """根据 action_type 创建操作回调。

        Args:
            action_type: 操作回调类型。
            context: 错误上下文。

        Returns:
            回调函数。
        """
        if action_type == "goto_cookie":
            return self._goto_cookie_page
        if action_type == "goto_settings":
            return self._goto_settings_page
        if action_type == "redownload":
            task_item_id = context.get("task_item_id", 0)
            return lambda: self._redownload(task_item_id)
        if action_type == "copy_details":
            details = context.get("details", "")
            return lambda: self._copy_error_details(details)
        # none 或未知
        return lambda: None

    def _goto_cookie_page(self) -> None:
        """跳转 Cookie 配置页。"""
        nav_bar = self._main_window._nav_bar  # noqa: SLF001
        if nav_bar is not None:
            nav_bar.set_current_page(2)

    def _goto_settings_page(self) -> None:
        """跳转设置页。"""
        nav_bar = self._main_window._nav_bar  # noqa: SLF001
        if nav_bar is not None:
            nav_bar.set_current_page(3)

    def _redownload(self, task_item_id: int) -> None:
        """重新加入下载队列。

        Args:
            task_item_id: 任务项 ID。
        """
        download_bridge = self._main_window._download_bridge  # noqa: SLF001
        control = download_bridge._control_signals  # noqa: SLF001
        control.start_download.emit([task_item_id])
        logger.info("已重新提交下载 task_item_id=%s", task_item_id)

    def _copy_error_details(self, details: str) -> None:
        """复制错误详情到剪贴板。

        Args:
            details: 错误详情文本。
        """
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and details:
            clipboard.setText(details)
        logger.debug("错误详情已复制到剪贴板")
