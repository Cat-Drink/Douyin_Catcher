"""设置页模块。

实现设置页，包含下载设置、元数据设置、日志与反馈、关于 4 个分组卡片。
配置变更时自动保存到 DB，并发 ``settings_changed`` 信号通知外部组件。

严格遵循设计文档 3.1 节页面 4 与 UIUX 规范 5.5 节。

布局结构::

    [56px 标题区: "设置"]
    [QScrollArea
        [下载设置卡片: 下载目录 / 并发下载数滑块 / 分块大小下拉 / 重试次数(固定)]
        [元数据设置卡片: JSON / CSV 勾选]
        [日志与反馈卡片: 日志位置 + 导出日志按钮]
        [关于卡片: 应用名/版本/设计参考 + 检查更新/开源仓库]
    ]
"""

from __future__ import annotations

import os
import sqlite3

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.config import LOG_DIR
from app.logger import get_logger
from app.repositories import ConfigRepository
from ui.widgets.toast import Toast

logger = get_logger(__name__)

# === 配置键 ===
_KEY_DOWNLOAD_DIR = "download_dir"
_KEY_CONCURRENCY = "concurrency"
_KEY_CHUNK_SIZE = "chunk_size"
_KEY_METADATA_FORMAT = "metadata_format"

# === 默认值 ===
_DEFAULT_CONCURRENCY = 3
_DEFAULT_CHUNK_SIZE = "1048576"  # 1MB
_DEFAULT_METADATA_FORMAT = "json"
_RETRIES_FIXED = 3  # 重试次数固定，不可改

# 分块大小选项：(显示文字, 字节数字符串)
_CHUNK_OPTIONS: list[tuple[str, str]] = [
    ("512 KB", "524288"),
    ("1 MB", "1048576"),
    ("2 MB", "2097152"),
    ("4 MB", "4194304"),
]

# 应用版本与开源仓库
_APP_VERSION = "v0.1.0"
_REPO_URL = "https://github.com/Evil0ctal/Douyin_TikTok_Download_API"


def _get_log_path() -> str:
    """返回日志文件路径（%APPDATA%/DouyinCatcher/logs/app.log）。"""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "DouyinCatcher", "logs", "app.log")


def _get_default_download_dir() -> str:
    """返回默认下载目录（用户下载目录下的 DouyinCatcher）。"""
    home = os.path.expanduser("~")
    return os.path.join(home, "Downloads", "DouyinCatcher")


class SettingsPage(QWidget):
    """设置页。

    信号:
        settings_changed: 任意配置项变更并保存后发射，传当前配置 dict。
        export_logs_requested: 点击"导出日志"按钮时发射。
    """

    settings_changed = Signal(dict)
    export_logs_requested = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        parent: QWidget | None = None,
    ) -> None:
        """初始化设置页。

        Args:
            conn: 数据库连接，供读写 config 表。
            parent: 父控件。
        """
        super().__init__(parent)
        self._conn = conn
        self._config_repo = ConfigRepository(conn)
        self._loading = False  # 标记 refresh 期间禁止触发自动保存
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        """构建页面布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题区
        title_label = QLabel("设置")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # 滚动内容区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 8, 24, 24)
        content_layout.setSpacing(24)

        # 4 个分组卡片
        content_layout.addWidget(self._create_download_card())
        content_layout.addWidget(self._create_metadata_card())
        content_layout.addWidget(self._create_log_card())
        content_layout.addWidget(self._create_about_card())
        content_layout.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _create_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """创建一个分组卡片容器，返回 (frame, content_layout)。"""
        frame = QFrame()
        frame.setObjectName("settingsCard")
        frame.setStyleSheet(
            "#settingsCard { background: #FFFFFF; border: 1px solid #E5E7EB;"
            " border-radius: 8px; }"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 16, 20, 16)
        frame_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        frame_layout.addWidget(title_label)
        return frame, frame_layout

    def _create_download_card(self) -> QFrame:
        """下载设置卡片。"""
        frame, layout = self._create_card("下载设置")

        # 下载目录
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_label = QLabel("下载目录:")
        dir_label.setMinimumWidth(100)
        dir_row.addWidget(dir_label)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择下载目录...")
        self._dir_edit.textChanged.connect(self._on_setting_changed)
        dir_row.addWidget(self._dir_edit, 1)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._on_browse_dir)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # 并发下载数滑块
        concurrency_row = QHBoxLayout()
        concurrency_row.setSpacing(8)
        concurrency_label = QLabel("并发下载数:")
        concurrency_label.setMinimumWidth(100)
        concurrency_row.addWidget(concurrency_label)
        self._concurrency_slider = QSlider(Qt.Orientation.Horizontal)
        self._concurrency_slider.setRange(1, 10)
        self._concurrency_slider.setValue(_DEFAULT_CONCURRENCY)
        self._concurrency_slider.valueChanged.connect(self._on_concurrency_changed)
        self._concurrency_slider.sliderReleased.connect(self._on_setting_changed)
        concurrency_row.addWidget(self._concurrency_slider, 1)
        self._concurrency_value = QLabel(str(_DEFAULT_CONCURRENCY))
        self._concurrency_value.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #7C3AED; min-width: 24px;"
        )
        self._concurrency_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        concurrency_row.addWidget(self._concurrency_value)
        layout.addLayout(concurrency_row)

        # 分块大小下拉
        chunk_row = QHBoxLayout()
        chunk_row.setSpacing(8)
        chunk_label = QLabel("分块大小:")
        chunk_label.setMinimumWidth(100)
        chunk_row.addWidget(chunk_label)
        self._chunk_combo = QComboBox()
        for text, _value in _CHUNK_OPTIONS:
            self._chunk_combo.addItem(text)
        self._chunk_combo.currentIndexChanged.connect(self._on_setting_changed)
        chunk_row.addWidget(self._chunk_combo, 1)
        layout.addLayout(chunk_row)

        # 重试次数（固定）
        retry_row = QHBoxLayout()
        retry_row.setSpacing(8)
        retry_label = QLabel("失败重试:")
        retry_label.setMinimumWidth(100)
        retry_row.addWidget(retry_label)
        retry_value = QLabel(f"{_RETRIES_FIXED} 次（固定）")
        retry_value.setStyleSheet("color: #9CA3AF;")
        retry_row.addWidget(retry_value)
        retry_row.addStretch(1)
        layout.addLayout(retry_row)

        return frame

    def _create_metadata_card(self) -> QFrame:
        """元数据设置卡片。"""
        frame, layout = self._create_card("元数据设置")

        hint = QLabel("选择下载后保存的元数据格式（至少保留一种）")
        hint.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(hint)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(16)
        self._json_chk = QCheckBox("JSON")
        self._json_chk.toggled.connect(self._on_metadata_toggled)
        fmt_row.addWidget(self._json_chk)
        self._csv_chk = QCheckBox("CSV")
        self._csv_chk.toggled.connect(self._on_metadata_toggled)
        fmt_row.addWidget(self._csv_chk)
        fmt_row.addStretch(1)
        layout.addLayout(fmt_row)

        return frame

    def _create_log_card(self) -> QFrame:
        """日志与反馈卡片。"""
        frame, layout = self._create_card("日志与反馈")

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_label = QLabel("日志位置:")
        path_label.setMinimumWidth(100)
        path_row.addWidget(path_label)
        log_path = _get_log_path()
        path_value = QLabel(log_path)
        path_value.setStyleSheet("color: #6B7280; font-size: 12px;")
        path_value.setWordWrap(True)
        path_row.addWidget(path_value, 1)
        layout.addLayout(path_row)

        export_row = QHBoxLayout()
        self._export_logs_btn = QPushButton("导出日志")
        self._export_logs_btn.clicked.connect(self._on_export_log_clicked)
        export_row.addWidget(self._export_logs_btn)
        export_row.addStretch(1)
        layout.addLayout(export_row)

        return frame

    def _create_about_card(self) -> QFrame:
        """关于卡片。"""
        frame, layout = self._create_card("关于")

        about_text = (
            f"抖音抓取器 (Douyin_Catcher)\n"
            f"版本: {_APP_VERSION}\n"
            f"设计参考: Evil0ctal/Douyin_TikTok_Download_API"
        )
        about_label = QLabel(about_text)
        about_label.setStyleSheet("color: #374151; font-size: 13px;")
        about_label.setWordWrap(True)
        layout.addWidget(about_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        check_update_btn = QPushButton("检查更新")
        check_update_btn.setEnabled(False)  # 首版不实现
        btn_row.addWidget(check_update_btn)
        repo_btn = QPushButton("开源仓库")
        repo_btn.clicked.connect(self._on_open_repo)
        btn_row.addWidget(repo_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return frame

    def refresh(self) -> None:
        """从 DB 加载配置，填充到各控件。"""
        self._loading = True
        try:
            config = self._config_repo.get_all()

            # 下载目录
            download_dir = config.get(_KEY_DOWNLOAD_DIR, "")
            if not download_dir:
                download_dir = _get_default_download_dir()
            self._dir_edit.setText(download_dir)

            # 并发数
            concurrency = config.get(_KEY_CONCURRENCY, "")
            try:
                concurrency_int = int(concurrency) if concurrency else _DEFAULT_CONCURRENCY
            except ValueError:
                concurrency_int = _DEFAULT_CONCURRENCY
            concurrency_int = max(1, min(10, concurrency_int))
            self._concurrency_slider.setValue(concurrency_int)
            self._concurrency_value.setText(str(concurrency_int))

            # 分块大小
            chunk_size = config.get(_KEY_CHUNK_SIZE, _DEFAULT_CHUNK_SIZE)
            chunk_index = 0
            for i, (_text, value) in enumerate(_CHUNK_OPTIONS):
                if value == chunk_size:
                    chunk_index = i
                    break
            self._chunk_combo.setCurrentIndex(chunk_index)

            # 元数据格式
            metadata_format = config.get(_KEY_METADATA_FORMAT, _DEFAULT_METADATA_FORMAT)
            self._json_chk.setChecked("json" in metadata_format)
            self._csv_chk.setChecked("csv" in metadata_format)
        finally:
            self._loading = False

    def _on_browse_dir(self) -> None:
        """浏览下载目录。"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if dir_path:
            self._dir_edit.setText(dir_path)

    def _on_concurrency_changed(self, value: int) -> None:
        """滑块拖动时实时显示数值（不保存，释放时保存）。"""
        self._concurrency_value.setText(str(value))

    def _on_metadata_toggled(self, _checked: bool) -> None:
        """元数据勾选变更：至少保留一种格式。"""
        if self._loading:
            return
        if not self._json_chk.isChecked() and not self._csv_chk.isChecked():
            # 阻止取消最后一个勾选：恢复刚被取消的
            sender = self.sender()
            if sender is self._json_chk:
                self._json_chk.setChecked(True)
            elif sender is self._csv_chk:
                self._csv_chk.setChecked(True)
            return
        self._on_setting_changed()

    def _on_setting_changed(self, *args) -> None:
        """任意配置项变更：保存到 DB 并发信号。"""
        if self._loading:
            return

        # 下载目录非空校验
        dir_path = self._dir_edit.text().strip()
        if not dir_path:
            self._dir_edit.setStyleSheet("border: 1px solid #EF4444;")
            return
        self._dir_edit.setStyleSheet("")

        # 组装配置 dict
        chunk_value = _CHUNK_OPTIONS[self._chunk_combo.currentIndex()][1]
        formats: list[str] = []
        if self._json_chk.isChecked():
            formats.append("json")
        if self._csv_chk.isChecked():
            formats.append("csv")
        metadata_format = ",".join(formats) if formats else _DEFAULT_METADATA_FORMAT

        config = {
            _KEY_DOWNLOAD_DIR: dir_path,
            _KEY_CONCURRENCY: str(self._concurrency_slider.value()),
            _KEY_CHUNK_SIZE: chunk_value,
            _KEY_METADATA_FORMAT: metadata_format,
        }

        # 保存到 DB
        try:
            for key, value in config.items():
                self._config_repo.set(key, value)
        except sqlite3.Error as e:
            logger.error("保存配置失败: %s", e)
            return

        logger.debug("配置已保存: %s", config)
        self.settings_changed.emit(config)
        Toast.show_success(self, "设置已保存")

    def _on_export_log_clicked(self) -> None:
        """导出日志按钮点击：打开日志目录。

        使用 ``QDesktopServices.openUrl`` + ``QUrl.fromLocalFile`` 打开
        ``app.config.LOG_DIR`` 目录。目录不存在时 Toast 提示"暂无日志文件"。
        """
        log_dir = str(LOG_DIR)
        if os.path.isdir(log_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))
            logger.info("已打开日志目录: %s", log_dir)
        else:
            Toast.show_warning(self, "暂无日志文件")
            logger.warning("日志目录不存在: %s", log_dir)

    def _on_open_repo(self) -> None:
        """打开开源仓库链接。"""
        QDesktopServices.openUrl(_REPO_URL)
