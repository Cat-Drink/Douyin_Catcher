"""导航栏组件模块。

实现左侧导航栏，包含 4 个导航项（下载任务/链接抓取/Cookie 配置/设置），
支持点击切换、互斥选中、选中项品牌紫高亮，底部固定下载任务状态栏。

严格遵循 UI/UX 规范 4.1 节（导航栏组件）与 v0.0.7 计划文档任务 4。
v0.1.2：底部新增下载任务状态栏（用户反馈 #14）。

视觉规范：
    - 导航栏宽 200px 固定，白色背景，右侧 1px 浅灰分隔线
    - 默认态：灰色文字 #6B7280，透明背景
    - Hover 态：深色文字 #111827，浅灰底 #F3F4F6
    - 选中态：品牌紫文字 #7C3AED，浅紫底 #F5F0FF，左侧 3px 品牌紫指示条
    - 底部固定显示下载任务统计 + 版本号
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class NavItem:
    """导航项数据。

    属性:
        text: 导航项显示文字。
        page_index: 对应 QStackedWidget 页面索引。
    """

    text: str
    page_index: int


# 导航项清单（硬编码常量，顺序对应 QStackedWidget 页面索引）
NAV_ITEMS: list[NavItem] = [
    NavItem(text="下载任务", page_index=0),
    NavItem(text="链接抓取", page_index=1),
    NavItem(text="Cookie 配置", page_index=2),
    NavItem(text="设置", page_index=3),
]


class NavBar(QWidget):
    """左侧导航栏组件。

    包含 Logo 区、4 个互斥导航项按钮、底部下载任务状态栏与版本号。
    点击导航项时发射 ``page_changed(int)`` 信号。

    信号:
        page_changed: 导航项被点击时发射，参数为目标页面索引。

    v0.1.2：新增 ``update_status`` 方法，用于主窗口全局刷新下载任务统计。
    """

    page_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化导航栏。

        Args:
            parent: 父控件。
        """
        super().__init__(parent)
        self.setObjectName("navBar")
        self._button_group: QButtonGroup | None = None
        self._nav_buttons: list[QPushButton] = []
        self._status_label: QLabel | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建导航栏布局：Logo + 导航项 + 弹性间距 + 状态栏 + 版本号。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo 区
        logo_label = QLabel("撷风拾影")
        logo_label.setObjectName("navLogo")
        layout.addWidget(logo_label)

        # 导航项按钮组（互斥选中）
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.idClicked.connect(self._on_item_clicked)
        for item in NAV_ITEMS:
            self._add_nav_item(item)

        # 弹性间距，将状态栏与版本号推到底部
        layout.addStretch(1)

        # v0.1.2：底部下载任务状态栏（固定显示在侧边栏底部）
        self._status_label = QLabel("总数 0 · 下载中 0 · 已完成 0 · 失败 0")
        self._status_label.setObjectName("navStatusBar")
        layout.addWidget(self._status_label)

        # 底部版本号（延迟导入避免循环依赖，版本号单一来源为 ui.main_window._APP_VERSION）
        from ui.main_window import _APP_VERSION

        version_label = QLabel(f"v{_APP_VERSION}")
        version_label.setObjectName("navVersion")
        layout.addWidget(version_label)

    def _add_nav_item(self, item: NavItem) -> None:
        """创建一个导航项按钮并加入按钮组。

        Args:
            item: 导航项数据。
        """
        button = QPushButton(item.text)
        button.setObjectName("navItem")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # 存储 page_index 到按钮属性，供点击回调读取
        button.setProperty("page_index", item.page_index)
        assert self._button_group is not None
        self._button_group.addButton(button)
        self._nav_buttons.append(button)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(button)

    def _on_item_clicked(self, button_id: int) -> None:
        """导航项点击回调。

        通过按钮组 ID 查找按钮，读取 page_index 并发射信号。

        Args:
            button_id: QButtonGroup 分配的按钮 ID。
        """
        assert self._button_group is not None
        button = self._button_group.button(button_id)
        if button is None:
            return
        page_index = button.property("page_index")
        if page_index is None:
            return
        logger.debug("导航项点击：page_index=%s", page_index)
        self.page_changed.emit(page_index)

    def set_current_page(self, index: int) -> None:
        """程序化设置当前选中页。

        更新对应按钮的 checked 状态。若 index 越界则忽略。

        Args:
            index: 目标页面索引（0-3）。
        """
        if not 0 <= index < len(self._nav_buttons):
            logger.warning("set_current_page index 越界: %s", index)
            return
        self._nav_buttons[index].setChecked(True)

    def update_status(self, total: int, downloading: int, completed: int, failed: int) -> None:
        """更新底部下载任务状态栏文字（v0.1.2）。

        Args:
            total: 总任务数。
            downloading: 下载中数。
            completed: 已完成数。
            failed: 失败数。
        """
        if self._status_label is None:
            return
        self._status_label.setText(
            f"总数 {total} · 下载中 {downloading} · 已完成 {completed} · 失败 {failed}"
        )
