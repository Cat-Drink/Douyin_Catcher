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

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
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
        """创建 4 个步骤子页面（任务 1 用占位，任务 2-5 替换）。"""
        # 任务 1：占位步骤，任务 2-5 逐步替换
        for i in range(_TOTAL_STEPS):
            placeholder = QWidget()
            label = QLabel(f"步骤 {i + 1}（待实现）")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 20px; color: #6B7280;")
            ph_layout = QVBoxLayout(placeholder)
            ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph_layout.addWidget(label)
            self._steps.append(placeholder)
            assert self._stacked is not None
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
