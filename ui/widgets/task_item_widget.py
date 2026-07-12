"""任务行组件模块。

实现单个下载任务项的行级展示组件，包含缩略图、信息区、类型标签、
进度条、操作按钮、失败原因。

严格遵循 UIUX 规范 4.5.1 节与设计文档 3.1 节页面 1 的任务行描述。

布局结构::

    [缩略图 64x64] [信息区: 标题/作者·时长] [类型标签] [进度条+百分比] [操作按钮]
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
from app.models import TaskItem
from ui.widgets.thumbnail_loader import ThumbnailLoader

logger = get_logger(__name__)

# 默认行高
_ROW_HEIGHT = 72
_ROW_HEIGHT_FAILED = 96
_THUMB_SIZE = 64

# 类型标签映射: type → (标签文字, objectName)
_TYPE_TAG_MAP: dict[str, tuple[str, str]] = {
    "video": ("视频", "tagVideo"),
    "image_set": ("图文", "tagImageSet"),
    "long_video": ("长视频", "tagLongVideo"),
}

# 占位缩略图（灰色 64x64）
_PLACEHOLDER_PIXMAP: QPixmap | None = None


def _get_placeholder_pixmap() -> QPixmap:
    """获取灰色占位图（延迟初始化）。"""
    global _PLACEHOLDER_PIXMAP
    if _PLACEHOLDER_PIXMAP is None:
        _PLACEHOLDER_PIXMAP = QPixmap(_THUMB_SIZE, _THUMB_SIZE)
        _PLACEHOLDER_PIXMAP.fill(Qt.GlobalColor.lightGray)
    return _PLACEHOLDER_PIXMAP


class TaskItemWidget(QWidget):
    """单个下载任务行组件。

    信号:
        pause_clicked: 状态为 downloading 时点击操作按钮，传 task_item_id。
        resume_clicked: 状态为 paused 时点击操作按钮，传 task_item_id。
        retry_clicked: 状态为 failed 时点击操作按钮，传 task_item_id。
        open_file_clicked: 状态为 completed 时点击操作按钮，传 local_path。
    """

    pause_clicked = Signal(int)
    resume_clicked = Signal(int)
    retry_clicked = Signal(int)
    open_file_clicked = Signal(str)

    def __init__(self, task_item: TaskItem, parent: QWidget | None = None) -> None:
        """初始化任务行。

        Args:
            task_item: 任务项数据。
            parent: 父控件。
        """
        super().__init__(parent)
        self._task_item = task_item
        self._thumb_loader: ThumbnailLoader | None = None
        self._setup_ui()
        self.update_from_task_item(task_item)

    def _setup_ui(self) -> None:
        """构建行布局。"""
        self.setFixedHeight(_ROW_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 缩略图
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._thumb_label.setScaledContents(True)
        self._thumb_label.setPixmap(_get_placeholder_pixmap())
        layout.addWidget(self._thumb_label)

        # 信息区（标题 + 元信息）
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        self._title_label = QLabel()
        self._title_label.setObjectName("taskTitle")
        info_layout.addWidget(self._title_label)
        self._meta_label = QLabel()
        self._meta_label.setObjectName("taskMeta")
        info_layout.addWidget(self._meta_label)
        layout.addLayout(info_layout, 1)

        # 类型标签
        self._type_label = QLabel()
        layout.addWidget(self._type_label)

        # 进度区（进度条 + 百分比）
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(2)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        progress_layout.addWidget(self._progress_bar)
        self._percent_label = QLabel()
        self._percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self._percent_label)
        layout.addLayout(progress_layout)

        # 操作按钮
        self._action_btn = QPushButton()
        self._action_btn.setFixedSize(32, 32)
        self._action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self._action_btn)

        # 失败原因（默认隐藏）
        self._fail_reason_label = QLabel()
        self._fail_reason_label.setObjectName("taskFailReason")
        self._fail_reason_label.setStyleSheet("color: #EF4444; font-size: 12px;")
        self._fail_reason_label.setVisible(False)
        layout.addWidget(self._fail_reason_label)

    def update_from_task_item(self, item: TaskItem) -> None:
        """根据 TaskItem 数据更新全部显示。

        Args:
            item: 任务项数据。
        """
        self._task_item = item

        # 标题
        self._title_label.setText(item.title or "未命名")

        # 元信息：作者·时长
        meta_parts: list[str] = []
        if item.author:
            meta_parts.append(item.author)
        if item.duration:
            meta_parts.append(item.duration)
        elif item.image_count:
            meta_parts.append(f"{item.image_count}张图")
        self._meta_label.setText(" · ".join(meta_parts) if meta_parts else "")

        # 类型标签
        type_tag = _TYPE_TAG_MAP.get(item.type or "video", ("视频", "tagVideo"))
        self._type_label.setText(type_tag[0])
        self._type_label.setObjectName(type_tag[1])
        self._type_label.setStyleSheet("padding: 2px 8px; border-radius: 4px; font-size: 12px;")

        # 缩略图异步加载
        if item.cover_url:
            self._load_thumbnail(item.cover_url)

        # 进度
        self.update_progress(item.downloaded_bytes, item.total_bytes)

        # 状态
        self.update_status(item.status, item.fail_reason)

    def _load_thumbnail(self, url: str) -> None:
        """异步加载缩略图。

        Args:
            url: 缩略图 URL。
        """
        if self._thumb_loader is None:
            self._thumb_loader = ThumbnailLoader(self)
            self._thumb_loader.loaded.connect(self._on_thumbnail_loaded)
        self._thumb_loader.load(url, (_THUMB_SIZE, _THUMB_SIZE))

    def _on_thumbnail_loaded(self, pixmap: QPixmap) -> None:
        """缩略图加载完成回调。"""
        if not pixmap.isNull():
            self._thumb_label.setPixmap(pixmap)

    def update_progress(self, downloaded: int, total: int) -> None:
        """更新进度条与百分比文字。

        Args:
            downloaded: 已下载字节数。
            total: 总字节数。
        """
        if total > 0:
            percent = int(downloaded * 100 / total)
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(percent)
            self._percent_label.setText(f"{percent}%")
        else:
            self._progress_bar.setRange(0, 0)
            self._percent_label.setText("等待中")

    def update_status(self, status: str, fail_reason: str | None = None) -> None:
        """更新状态显示。

        切换进度条颜色、操作按钮、失败态扩展。

        Args:
            status: 任务状态 (pending/downloading/paused/completed/failed)。
            fail_reason: 失败原因（仅 status=failed 时使用）。
        """
        self._task_item.status = status

        # 进度条颜色
        state_map = {
            "pending": "pending",
            "downloading": "downloading",
            "paused": "paused",
            "completed": "completed",
            "failed": "failed",
        }
        self._progress_bar.setProperty("state", state_map.get(status, ""))
        self._refresh_style(self._progress_bar)

        # 百分比文字
        status_text_map = {
            "pending": "等待中",
            "downloading": None,  # 由 update_progress 设置
            "paused": "已暂停",
            "completed": "完成",
            "failed": "失败",
        }
        text = status_text_map.get(status)
        if text is not None:
            self._percent_label.setText(text)

        # 操作按钮
        btn_map = {
            "pending": ("⏸", False),
            "downloading": ("⏸", True),
            "paused": ("▶", True),
            "completed": ("📁", True),
            "failed": ("🔄", True),
        }
        btn_text, enabled = btn_map.get(status, ("", False))
        self._action_btn.setText(btn_text)
        self._action_btn.setEnabled(enabled)

        # 失败态扩展
        if status == "failed":
            self.setFixedHeight(_ROW_HEIGHT_FAILED)
            reason = fail_reason or "未知错误"
            self._fail_reason_label.setText(f"失败原因：{reason}")
            self._fail_reason_label.setVisible(True)
            self.setStyleSheet(
                "TaskItemWidget { background-color: #FEF2F2; border-left: 3px solid #EF4444; }"
            )
        else:
            self.setFixedHeight(_ROW_HEIGHT)
            self._fail_reason_label.setVisible(False)
            self.setStyleSheet("")

    def _refresh_style(self, widget: QWidget) -> None:
        """刷新控件 QSS 样式（setProperty 后需要 unpolish/polish）。"""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _on_action_clicked(self) -> None:
        """操作按钮点击：根据状态发射对应信号。"""
        item_id = self._task_item.id
        if item_id is None:
            return
        status = self._task_item.status
        if status == "downloading":
            self.pause_clicked.emit(item_id)
        elif status == "paused":
            self.resume_clicked.emit(item_id)
        elif status == "failed":
            self.retry_clicked.emit(item_id)
        elif status == "completed" and self._task_item.local_path:
            self.open_file_clicked.emit(self._task_item.local_path)
