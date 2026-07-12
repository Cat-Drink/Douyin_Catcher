"""首次引导流程模块。

实现 4 步首次引导流程：欢迎 → 目录设置 → Cookie 配置 → 完成。
引导状态记录在 ``config`` 表，后续启动直接进主界面。

严格遵循设计文档第 7.4 节与 v0.0.9 计划文档。

引导流程状态机::

    应用启动
        │
        ▼
    onboarding_done == True?
        │
        ├─ 是 → 主界面
        │
        └─ 否 → OnboardingPage
                 │
                 ├─ 欢迎页(0) → "开始配置"
                 │      │
                 │      ▼
                 │   目录设置页(1) → "下一步"
                 │      │
                 │      ▼
                 │   Cookie 配置页(2) → 测试通过 → "完成"
                 │      │                    │
                 │      │                    ▼
                 │      │                 完成页(3) → "开始使用" → 主界面
                 │      │
                 │      └─ "跳过" → 主界面
                 │
                 └─ "跳过引导" → 主界面

本模块在任务 1 创建框架（4 个步骤用占位 QWidget），任务 2-5 逐步替换为实际子页面。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
from app.repositories import ConfigRepository, CookieRepository

if TYPE_CHECKING:
    from ui.error_handler import ErrorHandler
    from ui.main_window import MainWindow
    from worker.async_worker import AsyncWorker

logger = get_logger(__name__)

# 步骤指示器圆点样式
_DOT_CURRENT = (
    "min-width: 8px; min-height: 8px; max-width: 8px; max-height: 8px;"
    " border-radius: 4px; background-color: #7C3AED;"
)
_DOT_DONE = (
    "min-width: 8px; min-height: 8px; max-width: 8px; max-height: 8px;"
    " border-radius: 4px; background-color: #7C3AED;"
)
_DOT_PENDING = (
    "min-width: 8px; min-height: 8px; max-width: 8px; max-height: 8px;"
    " border-radius: 4px; background-color: #D1D5DB;"
)

# 总步骤数
_TOTAL_STEPS = 4


class OnboardingPage(QWidget):
    """首次引导流程页面。

    管理 4 步引导流程的页面切换、步骤指示器渲染、引导状态读写、
    与主窗口的跳转衔接。

    信号:
        onboarding_completed: 引导完成，主窗口收到后切换到下载任务页。
        onboarding_skipped: 引导被跳过，参数为 cookie_configured（是否已配置 Cookie）。
    """

    onboarding_completed = Signal()
    onboarding_skipped = Signal(bool)

    def __init__(
        self,
        config_repo: ConfigRepository,
        cookie_repo: CookieRepository,
        async_worker: AsyncWorker,
        main_window: MainWindow,
        error_handler: ErrorHandler,
        parent: QWidget | None = None,
    ) -> None:
        """初始化引导流程页面。

        Args:
            config_repo: 配置仓库（读写引导状态）。
            cookie_repo: Cookie 仓库（Cookie 步骤查询已有 Cookie）。
            async_worker: 异步工作线程（Cookie 测试异步调用）。
            main_window: 主窗口（引导完成后跳转主界面）。
            error_handler: 错误处理器（Cookie 测试失败错误处理）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._config_repo = config_repo
        self._cookie_repo = cookie_repo
        self._async_worker = async_worker
        self._main_window = main_window
        self._error_handler = error_handler
        self._current_step = 0
        self._cookie_valid = False

        # 步骤子页面（任务 2-5 替换占位）
        self._steps: list[QWidget] = []
        self._step_dots: list[QLabel] = []

        # 导航按钮
        self._prev_btn: QPushButton | None = None
        self._next_btn: QPushButton | None = None
        self._skip_btn: QPushButton | None = None
        self._stacked: QStackedWidget | None = None

        self._setup_ui()
        self._setup_steps()

    def _setup_ui(self) -> None:
        """构建整体布局：内容区 + 步骤指示器 + 底部导航。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 内容区（QStackedWidget）
        self._stacked = QStackedWidget()
        layout.addWidget(self._stacked, 1)

        # 步骤指示器（4 个圆点水平居中）
        indicator_widget = QWidget()
        indicator_widget.setFixedHeight(40)
        indicator_layout = QHBoxLayout(indicator_widget)
        indicator_layout.setContentsMargins(24, 8, 24, 8)
        indicator_layout.setSpacing(12)
        indicator_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for _i in range(_TOTAL_STEPS):
            dot = QLabel()
            dot.setStyleSheet(_DOT_PENDING)
            self._step_dots.append(dot)
            indicator_layout.addWidget(dot)
        layout.addWidget(indicator_widget)

        # 底部导航按钮区
        nav_widget = QWidget()
        nav_widget.setFixedHeight(64)
        nav_widget.setStyleSheet("border-top: 1px solid #E5E7EB;")
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(24, 12, 24, 12)
        nav_layout.setSpacing(12)

        self._skip_btn = QPushButton("跳过引导")
        self._skip_btn.setObjectName("textBtn")
        self._skip_btn.clicked.connect(self._skip_onboarding)
        nav_layout.addWidget(self._skip_btn)

        nav_layout.addStretch(1)

        self._prev_btn = QPushButton("上一步")
        self._prev_btn.clicked.connect(self._prev_step)
        nav_layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton("开始配置")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.clicked.connect(self._next_step)
        nav_layout.addWidget(self._next_btn)

        layout.addWidget(nav_widget)

    def _setup_steps(self) -> None:
        """创建 4 个步骤子页面。

        步骤 0 用 WelcomeStep（任务 2），步骤 1 用 DirectoryStep（任务 3），
        步骤 2-3 仍用占位（任务 4-5 替换）。
        """
        assert self._stacked is not None

        # 步骤 0：欢迎页（任务 2 已实现）
        welcome = WelcomeStep()
        self._steps.append(welcome)
        self._stacked.addWidget(welcome)

        # 步骤 1：目录设置页（任务 3 已实现）
        directory = DirectoryStep(self._config_repo)
        self._steps.append(directory)
        self._stacked.addWidget(directory)

        # 步骤 2-3：占位（任务 4-5 逐步替换）
        for i in range(2, _TOTAL_STEPS):
            placeholder = QWidget()
            label = QLabel(f"步骤 {i + 1}（待实现）")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 20px; color: #6B7280;")
            ph_layout = QVBoxLayout(placeholder)
            ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph_layout.addWidget(label)
            self._steps.append(placeholder)
            self._stacked.addWidget(placeholder)

        self._update_step_indicator()
        self._update_nav_buttons()

    def start(self) -> None:
        """启动引导流程：重置到第 1 步（欢迎页），显示 OnboardingPage。"""
        self._current_step = 0
        self._cookie_valid = False
        self._go_to_step(0)
        self.show()
        logger.info("引导流程已启动")

    def _go_to_step(self, step_index: int) -> None:
        """切换到指定步骤（0-3）。

        Args:
            step_index: 目标步骤索引。
        """
        if not 0 <= step_index < _TOTAL_STEPS:
            logger.warning("无效步骤索引: %s", step_index)
            return
        self._current_step = step_index
        assert self._stacked is not None
        self._stacked.setCurrentIndex(step_index)
        self._update_step_indicator()
        self._update_nav_buttons()
        logger.debug("切换到步骤 %s", step_index)

    def _next_step(self) -> None:
        """进入下一步，若已是最后一步则触发完成。"""
        if self._current_step == _TOTAL_STEPS - 1:
            # 最后一步（完成页）的"开始使用"按钮
            self._complete_onboarding()
            return

        # 进入下一步前保存当前步骤数据
        self._save_current_step_data()

        self._go_to_step(self._current_step + 1)

    def _prev_step(self) -> None:
        """返回上一步，第 1 步时禁用。"""
        if self._current_step > 0:
            self._go_to_step(self._current_step - 1)

    def _skip_onboarding(self) -> None:
        """跳过引导：设置 onboarding_done=1，发 onboarding_skipped 信号。"""
        cookie_configured = self._check_cookie_configured()
        self._config_repo.set_onboarding_done(True)
        logger.info("引导已跳过，cookie_configured=%s", cookie_configured)
        self.onboarding_skipped.emit(cookie_configured)

    def _complete_onboarding(self) -> None:
        """完成引导：设置 onboarding_done=1，发 onboarding_completed 信号。"""
        self._config_repo.set_onboarding_done(True)
        logger.info("引导已完成")
        self.onboarding_completed.emit()

    def _save_current_step_data(self) -> None:
        """进入下一步前保存当前步骤数据。

        各步骤子页面若需要保存数据，实现 ``save_data()`` 方法。
        """
        current_widget = self._steps[self._current_step]
        save_data = getattr(current_widget, "save_data", None)
        if callable(save_data):
            save_data()

    def _update_step_indicator(self) -> None:
        """刷新步骤指示器圆点状态（当前/已完成/未完成）。"""
        for i, dot in enumerate(self._step_dots):
            if i < self._current_step:
                dot.setStyleSheet(_DOT_DONE)
            elif i == self._current_step:
                dot.setStyleSheet(_DOT_CURRENT)
            else:
                dot.setStyleSheet(_DOT_PENDING)

    def _update_nav_buttons(self) -> None:
        """刷新底部导航按钮显隐与启用状态（按当前步骤）。"""
        assert self._prev_btn is not None
        assert self._next_btn is not None
        assert self._skip_btn is not None

        # 主操作按钮文字与启用状态
        next_btn_map = {
            0: ("开始配置", True),
            1: ("下一步", True),
            2: ("完成", self._cookie_valid),
            3: ("开始使用", True),
        }
        btn_text, enabled = next_btn_map.get(self._current_step, ("下一步", True))
        self._next_btn.setText(btn_text)
        self._next_btn.setEnabled(enabled)

        # 上一步按钮显隐
        self._prev_btn.setVisible(self._current_step in (1, 2))

        # 跳过按钮显隐与文字
        if self._current_step in (0, 1):
            self._skip_btn.setText("跳过引导")
            self._skip_btn.setVisible(True)
        elif self._current_step == 2:
            self._skip_btn.setText("跳过，稍后配置")
            self._skip_btn.setVisible(True)
        else:
            # 完成页不显示跳过
            self._skip_btn.setVisible(False)

    def _check_cookie_configured(self) -> bool:
        """查询 CookieRepository 是否有至少一条 Cookie。

        Returns:
            是否已配置 Cookie。
        """
        cookies = self._cookie_repo.get_all()
        return len(cookies) > 0

    def set_cookie_valid(self, valid: bool) -> None:
        """设置 Cookie 测试结果，控制"完成"按钮启用状态。

        由 CookieStep 在测试通过后调用。

        Args:
            valid: Cookie 是否有效。
        """
        self._cookie_valid = valid
        self._update_nav_buttons()


# === 应用图标路径（与 main.py 一致） ===
_ICON_PATH = Path(__file__).parent.parent.parent / "assets" / "icon.ico"

# 功能特性文案
_FEATURE_LINES: list[str] = [
    "下载抖音视频/图文/长视频",
    "批量链接下载",
    "用户主页批量抓取",
    "断点续传",
]


class WelcomeStep(QWidget):
    """欢迎页步骤（步骤 0）。

    展示应用 Logo、名称、功能简介，引导用户点击"开始配置"进入下一步。
    按钮由 OnboardingPage 底部导航区统一管理，本类只负责内容区。

    信号:
        start_clicked: 预留信号（OnboardingPage 底部"开始配置"按钮触发进入下一步）。
    """

    start_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化欢迎页。

        Args:
            parent: 父控件。
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建欢迎页布局（垂直居中）。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 应用 Logo 128x128
        logo_label = QLabel()
        logo_label.setFixedSize(128, 128)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(_ICON_PATH))
        if pixmap.isNull():
            # Logo 加载失败：灰色占位块
            logo_label.setStyleSheet("background-color: #E5E7EB; border-radius: 16px;")
        else:
            logo_label.setPixmap(
                pixmap.scaled(
                    128,
                    128,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 应用名称
        title_label = QLabel("欢迎使用抖音抓取器")
        title_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel("一款让你轻松下载抖音视频的桌面工具")
        subtitle_label.setStyleSheet("font-size: 14px; color: #6B7280;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label)

        # 间距
        layout.addSpacing(16)

        # 功能特性标题
        features_title = QLabel("功能特性：")
        features_title.setStyleSheet("font-size: 14px; font-weight: 500;")
        layout.addWidget(features_title)

        # 功能列表
        for line in _FEATURE_LINES:
            feature_label = QLabel(f"• {line}")
            feature_label.setStyleSheet("font-size: 14px; color: #6B7280;")
            layout.addWidget(feature_label)


class DirectoryStep(QWidget):
    """下载目录设置页步骤（步骤 1）。

    引导用户选择下载文件保存位置，默认 ``%USERPROFILE%/Downloads/DouyinCatcher``，
    可修改，并校验目录可读性。

    信号:
        directory_valid: 目录校验通过，参数为目录路径。
        directory_invalid: 目录校验失败，参数为错误原因。
    """

    directory_valid = Signal(str)
    directory_invalid = Signal(str)

    def __init__(
        self,
        config_repo: ConfigRepository,
        parent: QWidget | None = None,
    ) -> None:
        """初始化目录设置页。

        Args:
            config_repo: 配置仓库（读写下载目录到 config 表）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._config_repo = config_repo
        self._dir_edit: QLineEdit | None = None
        self._error_label: QLabel | None = None
        self._setup_ui()
        self._load_default_directory()

    def _setup_ui(self) -> None:
        """构建目录设置页布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(12)

        # 步骤标题
        title = QLabel("步骤 1：设置下载目录")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        # 说明文字
        desc = QLabel("选择视频文件保存的位置，建议使用默认目录。")
        desc.setStyleSheet("font-size: 14px; color: #6B7280;")
        layout.addWidget(desc)

        # 目录输入框 + 浏览按钮
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择下载目录...")
        self._dir_edit.textChanged.connect(self._on_directory_changed)
        dir_row.addWidget(self._dir_edit, 1)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # 提示信息
        hint = QLabel("默认目录为系统下载文件夹下的 DouyinCatcher 子文件夹，" "可随时在设置中修改")
        hint.setStyleSheet("font-size: 12px; color: #3B82F6;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 错误提示（默认隐藏）
        self._error_label = QLabel()
        self._error_label.setStyleSheet("font-size: 12px; color: #EF4444;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        layout.addStretch(1)

    def _load_default_directory(self) -> str:
        """返回默认目录：优先读 config 表 download_dir，无值则用 DEFAULT_DOWNLOAD_DIR。

        Returns:
            默认目录路径。
        """
        from app.config import DEFAULT_DOWNLOAD_DIR

        download_dir = self._config_repo.get("download_dir")
        if not download_dir:
            download_dir = str(DEFAULT_DOWNLOAD_DIR)
        assert self._dir_edit is not None
        self._dir_edit.setText(download_dir)
        return download_dir

    def _on_browse_clicked(self) -> None:
        """点击浏览按钮：弹出 QFileDialog，用户选择后更新输入框并触发校验。"""
        assert self._dir_edit is not None
        dir_path = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if dir_path:
            self._dir_edit.setText(dir_path)

    def _validate_directory(self, path: str) -> tuple[bool, str]:
        """校验目录可读性。

        校验步骤：
            1. 路径非空检查
            2. 目录创建检查（mkdir parents=True, exist_ok=True）
            3. 写入权限检查（创建临时文件并删除）

        Args:
            path: 目录路径。

        Returns:
            (是否有效, 错误原因) 元组。
        """
        if not path:
            return False, "请选择下载目录"
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError:
            return False, "目录无法创建，请选择其他位置"
        # 写入权限检查
        try:
            test_file = Path(path) / ".douyin_catcher_test"
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
        except OSError:
            return False, "目录无写入权限，请选择其他位置"
        return True, ""

    def _on_directory_changed(self, path: str) -> None:
        """目录输入变化时触发校验。

        Args:
            path: 当前输入的目录路径。
        """
        valid, reason = self._validate_directory(path)
        assert self._dir_edit is not None
        assert self._error_label is not None
        if valid:
            self._dir_edit.setStyleSheet("")
            self._error_label.setVisible(False)
            self.directory_valid.emit(path)
        else:
            self._dir_edit.setStyleSheet("border: 1px solid #EF4444;")
            self._error_label.setText(f"⚠ {reason}")
            self._error_label.setVisible(True)
            self.directory_invalid.emit(reason)

    def save_directory(self) -> None:
        """保存目录到 config 表（ConfigRepository.set("download_dir", path)）。"""
        path = self.get_directory()
        if path:
            self._config_repo.set("download_dir", path)
            logger.info("下载目录已保存: %s", path)

    def get_directory(self) -> str:
        """返回当前输入框中的目录路径。"""
        assert self._dir_edit is not None
        return self._dir_edit.text().strip()

    def save_data(self) -> None:
        """供 OnboardingPage._save_current_step_data 调用。"""
        self.save_directory()
