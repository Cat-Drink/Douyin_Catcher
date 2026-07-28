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

import concurrent.futures
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
from app.models import Cookie
from app.repositories import ConfigRepository, CookieRepository
from crawlers.cookie_tester import CookieTester, CookieTestResult

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
        cookie_tester: CookieTester,
        main_window: MainWindow,
        error_handler: ErrorHandler,
        parent: QWidget | None = None,
    ) -> None:
        """初始化引导流程页面。

        Args:
            config_repo: 配置仓库（读写引导状态）。
            cookie_repo: Cookie 仓库（Cookie 步骤查询已有 Cookie）。
            async_worker: 异步工作线程（Cookie 测试异步调用）。
            cookie_tester: Cookie 测试器（异步测试 Cookie 有效性）。
            main_window: 主窗口（引导完成后跳转主界面）。
            error_handler: 错误处理器（Cookie 测试失败错误处理）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._config_repo = config_repo
        self._cookie_repo = cookie_repo
        self._async_worker = async_worker
        self._cookie_tester = cookie_tester
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
        步骤 2 用 CookieStep（任务 4），步骤 3 仍用占位（任务 5 替换）。
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

        # 步骤 2：Cookie 配置页（任务 4 已实现）
        cookie = CookieStep(
            self._cookie_repo,
            self._async_worker,
            self._cookie_tester,
            self._error_handler,
        )
        cookie.cookie_valid.connect(lambda: self.set_cookie_valid(True))
        cookie.cookie_test_started.connect(lambda: logger.info("Cookie 测试开始"))
        cookie.cookie_test_finished.connect(lambda: logger.info("Cookie 测试结束"))
        self._steps.append(cookie)
        self._stacked.addWidget(cookie)

        # 步骤 3：完成页（任务 5 已实现）
        complete = CompleteStep(cookie_configured=True)
        self._steps.append(complete)
        self._stacked.addWidget(complete)

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
        # 进入完成页时刷新 Cookie 配置状态
        if step_index == 3:
            complete_step = self._steps[3]
            if isinstance(complete_step, CompleteStep):
                complete_step.set_cookie_configured(self._check_cookie_configured())
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
        title_label = QLabel("欢迎使用撷风拾影")
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

    引导用户选择下载文件保存位置，默认 ``%USERPROFILE%/Downloads/XieFengShiYing``，
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
        hint = QLabel("默认目录为系统下载文件夹下的 XieFengShiYing 子文件夹，" "可随时在设置中修改")
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
            test_file = Path(path) / ".xiefeng_shiying_test"
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


# === Cookie 配置引导页（任务 4） ===

# 简版教程步骤（3 步，与完整版 7 步区分）
_BRIEF_TUTORIAL_STEPS: list[str] = [
    "1. 浏览器打开 douyin.com 并登录",
    "2. 按 F12 打开开发者工具 → Network",
    "3. 刷新页面，点任意请求，复制 Request Headers 里的 Cookie 值",
]


class CookieStep(QWidget):
    """Cookie 配置引导页步骤（步骤 2）。

    引导用户添加第一个 Cookie 并测试通过，支持查看完整教程、
    允许跳过（提示后续可配置）。

    信号:
        cookie_valid: Cookie 测试通过并保存，OnboardingPage 据此启用"完成"按钮。
        cookie_test_started: 开始测试 Cookie（用于显示 Loading）。
        cookie_test_finished: 测试结束（无论成功失败，用于隐藏 Loading）。
    """

    cookie_valid = Signal()
    cookie_test_started = Signal()
    cookie_test_finished = Signal()

    # 内部信号：异步测试结果从工作线程回传到 UI 线程
    _test_result_ready = Signal(object)  # CookieTestResult

    def __init__(
        self,
        cookie_repo: CookieRepository,
        async_worker: AsyncWorker,
        cookie_tester: CookieTester,
        error_handler: ErrorHandler,
        parent: QWidget | None = None,
    ) -> None:
        """初始化 Cookie 配置引导页。

        Args:
            cookie_repo: Cookie 仓库（保存测试通过的 Cookie）。
            async_worker: 异步工作线程（异步测试 Cookie）。
            cookie_tester: Cookie 测试器（调用 test_cookie 验证有效性）。
            error_handler: 错误处理器（输入校验错误展示）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._cookie_repo = cookie_repo
        self._async_worker = async_worker
        self._cookie_tester = cookie_tester
        self._error_handler = error_handler
        self._testing = False
        self._cookie_edit: QPlainTextEdit | None = None
        self._label_edit: QLineEdit | None = None
        self._test_btn: QPushButton | None = None
        self._result_label: QLabel | None = None
        self._tutorial_container: QFrame | None = None
        self._tutorial_btn: QPushButton | None = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """构建 Cookie 配置引导页布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(12)

        # 步骤标题
        title = QLabel("步骤 2：配置 Cookie")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        # 说明文字
        desc = QLabel("抖音需要登录态才能访问视频数据，请按教程获取 Cookie。")
        desc.setStyleSheet("font-size: 14px; color: #6B7280;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 简版教程卡片
        tutorial_card = QFrame()
        tutorial_card.setStyleSheet(
            "QFrame { background-color: #F9FAFB;"
            " border: 1px solid #E5E7EB; border-radius: 8px; }"
        )
        card_layout = QVBoxLayout(tutorial_card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(6)

        card_title = QLabel("Cookie 获取教程（简版）")
        card_title.setStyleSheet("font-size: 14px; font-weight: 500;")
        card_layout.addWidget(card_title)

        for step_text in _BRIEF_TUTORIAL_STEPS:
            step_label = QLabel(step_text)
            step_label.setStyleSheet("font-size: 13px; color: #374151;")
            step_label.setWordWrap(True)
            card_layout.addWidget(step_label)

        # 查看详细教程链接
        self._tutorial_btn = QPushButton("查看详细教程 ▼")
        self._tutorial_btn.setObjectName("textBtn")
        self._tutorial_btn.clicked.connect(self._toggle_tutorial)
        card_layout.addWidget(self._tutorial_btn)

        layout.addWidget(tutorial_card)

        # 完整教程区（可折叠，默认隐藏）
        self._tutorial_container = self._create_full_tutorial()
        self._tutorial_container.setVisible(False)
        layout.addWidget(self._tutorial_container)

        # Cookie 内容标签
        content_label = QLabel("Cookie 内容")
        content_label.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(content_label)

        # Cookie 文本框
        self._cookie_edit = QPlainTextEdit()
        self._cookie_edit.setFixedHeight(120)
        self._cookie_edit.setPlaceholderText("在此粘贴 Cookie 字符串...")
        layout.addWidget(self._cookie_edit)

        # 标签
        label_label = QLabel("标签")
        label_label.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(label_label)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("如：账号1")
        self._label_edit.setText("账号1")
        layout.addWidget(self._label_edit)

        # 添加并测试按钮
        self._test_btn = QPushButton("添加并测试")
        self._test_btn.setObjectName("primaryBtn")
        self._test_btn.clicked.connect(self._on_test_clicked)
        layout.addWidget(self._test_btn)

        # 测试结果反馈区（默认隐藏）
        self._result_label = QLabel()
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)

        layout.addStretch(1)

    def _create_full_tutorial(self) -> QFrame:
        """创建完整教程区（7 步，复用 CookiePage 的教程数据）。"""
        from ui.pages.cookie_page import _TUTORIAL_STEPS

        widget = QFrame()
        widget.setStyleSheet(
            "QFrame { background-color: #F9FAFB;"
            " border: 1px solid #E5E7EB; border-radius: 8px; }"
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        full_title = QLabel("Cookie 获取教程（完整版）")
        full_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(full_title)

        for step_title, step_desc in _TUTORIAL_STEPS:
            step_layout = QVBoxLayout()
            step_layout.setSpacing(4)
            t_label = QLabel(step_title)
            t_label.setStyleSheet("font-size: 13px; font-weight: 500;")
            step_layout.addWidget(t_label)
            d_label = QLabel(step_desc)
            d_label.setStyleSheet("color: #6B7280; font-size: 12px;")
            d_label.setWordWrap(True)
            step_layout.addWidget(d_label)
            layout.addLayout(step_layout)

        return widget

    def _connect_signals(self) -> None:
        """连接内部信号。"""
        self._test_result_ready.connect(self._on_test_result)

    def _toggle_tutorial(self) -> None:
        """展开/收起完整教程区。"""
        assert self._tutorial_container is not None
        assert self._tutorial_btn is not None
        visible = self._tutorial_container.isVisible()
        self._tutorial_container.setVisible(not visible)
        self._tutorial_btn.setText("查看详细教程 ▲" if not visible else "查看详细教程 ▼")

    def _validate_input(self, content: str) -> tuple[bool, str]:
        """校验 Cookie 内容非空、长度合理。

        Args:
            content: Cookie 内容字符串。

        Returns:
            (是否有效, 错误原因) 元组。
        """
        if not content:
            return False, "请输入 Cookie 内容"
        if len(content) < 20:
            return False, "Cookie 内容过短，请确认已完整复制"
        return True, ""

    def _on_test_clicked(self) -> None:
        """点击"添加并测试"：校验输入 → 发 cookie_test_started → 异步测试。"""
        assert self._cookie_edit is not None
        assert self._label_edit is not None
        assert self._test_btn is not None

        content = self._cookie_edit.toPlainText().strip()
        label = self._label_edit.text().strip() or "账号1"

        valid, reason = self._validate_input(content)
        if not valid:
            self._error_handler.show_input_error(self._cookie_edit, reason)
            return
        self._error_handler.clear_input_error(self._cookie_edit)

        self._testing = True
        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")
        self._hide_result()
        self.cookie_test_started.emit()
        logger.info("开始异步测试 Cookie，label=%s", label)

        future = self._async_worker.submit(self._cookie_tester.test_cookie(content))
        future.add_done_callback(self._on_future_done)

    def _on_future_done(self, future: concurrent.futures.Future) -> None:
        """工作线程回调：提取结果后通过信号回传到 UI 线程。

        Args:
            future: concurrent.futures.Future，持有 CookieTestResult。
        """
        try:
            result = future.result()
        except Exception as e:
            logger.exception("Cookie 测试异常")
            result = CookieTestResult(is_valid=False, error_message=str(e), user_nickname=None)
        self._test_result_ready.emit(result)

    def _on_test_result(self, result: CookieTestResult) -> None:
        """UI 线程：处理测试结果。

        成功则保存 Cookie + 发 cookie_valid；失败则显示原因。

        Args:
            result: Cookie 测试结果。
        """
        assert self._test_btn is not None
        assert self._cookie_edit is not None
        assert self._label_edit is not None

        self._testing = False
        self._test_btn.setEnabled(True)
        self._test_btn.setText("添加并测试")

        if result.is_valid:
            content = self._cookie_edit.toPlainText().strip()
            label = self._label_edit.text().strip() or "账号1"
            self._save_cookie(content, label)
            self._show_success(result.user_nickname)
            self.cookie_valid.emit()
        else:
            self._show_failure(result.error_message)

        self.cookie_test_finished.emit()

    def _save_cookie(self, content: str, label: str) -> int:
        """保存 Cookie 到 cookies 表。

        Args:
            content: Cookie 内容。
            label: Cookie 标签。

        Returns:
            新建的 cookie_id。
        """
        cookie = Cookie(
            id=None,
            content=content,
            label=label,
            status="valid",
        )
        cookie_id = self._cookie_repo.add(cookie)
        logger.info("Cookie 已保存，id=%s, label=%s", cookie_id, label)
        return cookie_id

    def _show_success(self, nickname: str | None) -> None:
        """显示成功反馈。

        Args:
            nickname: 用户昵称（可选）。
        """
        assert self._result_label is not None
        msg = "Cookie 有效，可以开始使用"
        if nickname:
            msg = f"Cookie 有效（账号：{nickname}），可以开始使用"
        self._result_label.setText(f"✓ {msg}")
        self._result_label.setStyleSheet("font-size: 14px; color: #10B981;")
        self._result_label.setVisible(True)

    def _show_failure(self, reason: str) -> None:
        """显示失败反馈。

        Args:
            reason: 失败原因。
        """
        assert self._result_label is not None
        self._result_label.setText(f"✖ 测试失败：{reason}，请重新输入")
        self._result_label.setStyleSheet("font-size: 14px; color: #EF4444;")
        self._result_label.setVisible(True)

    def _hide_result(self) -> None:
        """隐藏测试结果反馈区。"""
        assert self._result_label is not None
        self._result_label.setVisible(False)

    def save_data(self) -> None:
        """供 OnboardingPage._save_current_step_data 调用。

        Cookie 在测试通过时已保存，此处无需重复保存。
        """
        pass


# === 完成页（任务 5） ===


class CompleteStep(QWidget):
    """完成页步骤（步骤 3）。

    展示"配置完成"信息，引导用户点击"开始使用"进入主界面。
    按钮由 OnboardingPage 底部导航区统一管理，本类只负责内容区。

    信号:
        enter_app_clicked: 预留信号（OnboardingPage 底部"开始使用"按钮触发完成）。
    """

    enter_app_clicked = Signal()

    def __init__(
        self,
        cookie_configured: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """初始化完成页。

        Args:
            cookie_configured: 是否已配置 Cookie，用于决定是否显示 Cookie 未配置提示。
            parent: 父控件。
        """
        super().__init__(parent)
        self._cookie_configured = cookie_configured
        self._warning_label: QLabel | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建完成页布局（垂直居中）。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 完成图标 64x64（绿色圆形 + 白色 ✓）
        icon_label = QLabel("✓")
        icon_label.setFixedSize(64, 64)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            "background-color: #10B981; color: #FFFFFF;"
            " border-radius: 32px; font-size: 32px; font-weight: bold;"
        )
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 完成标题
        title_label = QLabel("配置完成！")
        title_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 说明文字
        desc_label = QLabel('现在可以开始下载抖音视频了\n前往"链接抓取"页粘贴链接即可开始')
        desc_label.setStyleSheet("font-size: 14px; color: #6B7280;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)

        # Cookie 未配置提示（条件显示）
        self._warning_label = QLabel(
            "⚠ Cookie 未配置，部分功能不可用，请稍后在 Cookie 配置页完成配置"
        )
        self._warning_label.setStyleSheet("font-size: 12px; color: #F59E0B;")
        self._warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(not self._cookie_configured)
        layout.addWidget(self._warning_label)

    def set_cookie_configured(self, configured: bool) -> None:
        """更新 Cookie 配置状态，控制未配置提示的显隐。

        Args:
            configured: 是否已配置 Cookie。
        """
        self._cookie_configured = configured
        if self._warning_label is not None:
            self._warning_label.setVisible(not configured)
