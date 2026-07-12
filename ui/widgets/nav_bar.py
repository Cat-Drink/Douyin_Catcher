"""导航栏组件模块。

实现左侧导航栏，包含 4 个导航项（下载任务/链接抓取/Cookie 配置/设置），
支持点击切换、互斥选中、选中项品牌紫高亮。

严格遵循 UI/UX 规范 4.1 节（导航栏组件）与 v0.0.7 计划文档任务 4。

视觉规范：
    - 导航栏宽 200px 固定，白色背景，右侧 1px 浅灰分隔线
    - 默认态：灰色文字 #6B7280，透明背景
    - Hover 态：深色文字 #111827，浅灰底 #F3F4F6
    - 选中态：品牌紫文字 #7C3AED，浅紫底 #F5F0FF，左侧 3px 品牌紫指示条
    - 底部显示版本号
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

# 应用版本号（与 main.py 的 APP_VERSION 保持一致）
_NAV_VERSION = "v0.0.7"


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

    包含 Logo 区、4 个互斥导航项按钮、底部版本号。
    点击导航项时发射 ``page_changed(int)`` 信号。

    信号:
        page_changed: 导航项被点击时发射，参数为目标页面索引。
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
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建导航栏布局：Logo + 导航项 + 弹性间距 + 版本号。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo 区
        logo_label = QLabel("Douyin Catcher")
        logo_label.setObjectName("navLogo")
        layout.addWidget(logo_label)

        # 导航项按钮组（互斥选中）
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for item in NAV_ITEMS:
            self._add_nav_item(item)

        # 弹性间距，将版本号推到底部
        layout.addStretch(1)

        # 底部版本号
        version_label = QLabel(_NAV_VERSION)
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
        self._button_group.idClicked.connect(self._on_item_clicked)
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
