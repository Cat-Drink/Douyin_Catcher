"""主页过滤栏组件模块。

实现主页抓取过滤条件栏，包含类型下拉、数量上限、时间段、开始抓取按钮。
供链接抓取页在检测到主页链接时显示。

严格遵循设计文档 3.1 节页面 2 过滤栏与 UIUX 规范 5.3 节。

布局结构::

    [类型: 下拉] [数量上限: SpinBox] [时间段: 起DateEdit 至DateEdit] [开始抓取按钮]
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from app.logger import get_logger

logger = get_logger(__name__)

# 类型下拉选项: (显示文字, filters type 值)
_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("全部", "all"),
    ("视频", "video"),
    ("图文", "image_set"),
    ("长视频", "long_video"),
]


class FilterBar(QWidget):
    """主页抓取过滤条件栏。

    信号:
        fetch_requested: 点击"开始抓取"按钮，传 filters dict
            （含 sec_user_id、type_filter、max_count、start_date、end_date）。
    """

    fetch_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化过滤栏。

        Args:
            parent: 父控件。
        """
        super().__init__(parent)
        self._sec_user_id: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建过滤栏布局。"""
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(12)

        # 类型下拉
        layout.addWidget(QLabel("类型:"))
        self._type_combo = QComboBox()
        for text, _ in _TYPE_OPTIONS:
            self._type_combo.addItem(text)
        self._type_combo.setFixedHeight(32)
        layout.addWidget(self._type_combo)

        # 数量上限
        layout.addWidget(QLabel("数量上限:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 500)
        self._count_spin.setValue(50)
        self._count_spin.setFixedHeight(32)
        self._count_spin.setFixedWidth(80)
        layout.addWidget(self._count_spin)

        # 时间段
        layout.addWidget(QLabel("时间段:"))
        self._date_start = QDateEdit()
        self._date_start.setCalendarPopup(True)
        self._date_start.setDate(QDate.currentDate().addDays(-30))
        self._date_start.setDisplayFormat("yyyy-MM-dd")
        self._date_start.setFixedHeight(32)
        layout.addWidget(self._date_start)

        layout.addWidget(QLabel("至"))

        self._date_end = QDateEdit()
        self._date_end.setCalendarPopup(True)
        self._date_end.setDate(QDate.currentDate())
        self._date_end.setDisplayFormat("yyyy-MM-dd")
        self._date_end.setFixedHeight(32)
        layout.addWidget(self._date_end)

        layout.addStretch(1)

        # 开始抓取按钮
        self._fetch_btn = QPushButton("开始抓取")
        self._fetch_btn.setObjectName("primaryBtn")
        self._fetch_btn.setFixedHeight(32)
        self._fetch_btn.clicked.connect(self._on_fetch_clicked)
        layout.addWidget(self._fetch_btn)

    def get_filters(self) -> dict:
        """收集当前过滤条件。

        Returns:
            含 sec_user_id、type_filter、max_count、start_date、end_date 的 dict。
        """
        type_idx = self._type_combo.currentIndex()
        type_filter = _TYPE_OPTIONS[type_idx][1] if 0 <= type_idx < len(_TYPE_OPTIONS) else "all"
        return {
            "sec_user_id": self._sec_user_id,
            "type_filter": type_filter,
            "max_count": self._count_spin.value(),
            "start_date": self._date_start.date().toString("yyyy-MM-dd"),
            "end_date": self._date_end.date().toString("yyyy-MM-dd"),
        }

    def set_sec_user_id(self, sec_user_id: str) -> None:
        """设置当前主页的 sec_user_id。

        Args:
            sec_user_id: 用户主页 sec_user_id。
        """
        self._sec_user_id = sec_user_id

    def set_loading(self, loading: bool) -> None:
        """设置抓取进行中的 loading 状态。

        Args:
            loading: True 时按钮变"抓取中..."并禁用，False 时恢复。
        """
        if loading:
            self._fetch_btn.setText("抓取中...")
            self._fetch_btn.setEnabled(False)
        else:
            self._fetch_btn.setText("开始抓取")
            self._fetch_btn.setEnabled(True)

    def _on_fetch_clicked(self) -> None:
        """开始抓取按钮点击。"""
        filters = self.get_filters()
        logger.debug("过滤栏发起抓取: %s", filters)
        self.fetch_requested.emit(filters)
