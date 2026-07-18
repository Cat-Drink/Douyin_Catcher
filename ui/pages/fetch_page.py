"""链接抓取页模块。

实现链接抓取页，包含多行链接输入、文件导入、解析、解析结果列表、
主页过滤栏、勾选下载全流程。

严格遵循设计文档 3.1 节页面 2 与 UIUX 规范 5.3 节。

布局结构::

    [56px 标题区: "链接抓取"]
    [输入区: QPlainTextEdit(120px) + 导入文件按钮]
    [操作行: 开始解析按钮          开始下载(N)]
    [提示行（检测到主页链接时）]
    [过滤栏（主页链接时显示）]
    [列表头: 全选 + 已选计数]
    [解析结果列表 QScrollArea]

v0.1.3：移除底部下载目录显示与浏览按钮，下载目录统一在设置页配置
（用户反馈 #9）。

v0.1.7：链接解析流程改为预览模式——解析后展示 PreviewItemWidget 列表，
图集类型可展开预览所有图片缩略图并支持图片级勾选（用户反馈 #7）。
原 ResultItemWidget 保留供主页抓取流程（PostItem）使用。
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
from app.preview_models import PreviewItem
from ui.widgets.filter_bar import FilterBar
from ui.widgets.loading_overlay import LoadingOverlay
from ui.widgets.thumbnail_loader import ThumbnailLoader
from ui.widgets.toast import Toast
from worker.crawler_bridge import CrawlerBridge

logger = get_logger(__name__)

# 类型标签映射
_TYPE_TAG_MAP: dict[str, tuple[str, str]] = {
    "video": ("视频", "tagVideo"),
    "image_set": ("图文", "tagImageSet"),
    "long_video": ("长视频", "tagLongVideo"),
    "user_home": ("主页", "tagVideo"),
}


class ResultItemWidget(QWidget):
    """解析结果行组件（UIUX 规范 4.5.3 节）。

    水平排列：``[勾选框] [缩略图 48x48] [标题] [作者] [类型标签] [时长/图片数]``

    信号:
        selection_changed: 勾选状态变化，传 is_selected。
    """

    selection_changed = Signal(bool)

    def __init__(self, result: dict, parent: QWidget | None = None) -> None:
        """初始化结果行。

        Args:
            result: 解析结果 dict，含 aweme_id/title/author/type/
                duration/image_count/cover_url 等字段。
            parent: 父控件。
        """
        super().__init__(parent)
        self._result = result
        self._thumb_loader: ThumbnailLoader | None = None
        self._setup_ui()
        self._fill_data()

    def _setup_ui(self) -> None:
        """构建行布局。"""
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # 勾选框
        self._chk = QCheckBox()
        self._chk.toggled.connect(self.selection_changed.emit)
        layout.addWidget(self._chk)

        # 缩略图
        self._thumb = QLabel()
        self._thumb.setFixedSize(48, 48)
        self._thumb.setScaledContents(True)
        self._thumb.setStyleSheet("background-color: #E5E7EB; border-radius: 4px;")
        layout.addWidget(self._thumb)

        # 标题
        self._title = QLabel()
        self._title.setStyleSheet("font-size: 14px; font-weight: 500;")
        self._title.setMinimumWidth(200)
        layout.addWidget(self._title, 1)

        # 作者
        self._author = QLabel()
        self._author.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(self._author)

        # 类型标签
        self._type_label = QLabel()
        self._type_label.setStyleSheet("padding: 2px 8px; border-radius: 4px; font-size: 12px;")
        layout.addWidget(self._type_label)

        # 时长/图片数
        self._duration = QLabel()
        self._duration.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(self._duration)

    def _fill_data(self) -> None:
        """填充数据到各控件。"""
        self._title.setText(self._result.get("title", "") or "未命名")
        self._author.setText(self._result.get("author", "") or "")

        # 类型标签
        item_type = self._result.get("type", "video")
        tag_text, tag_obj = _TYPE_TAG_MAP.get(item_type, ("视频", "tagVideo"))
        self._type_label.setText(tag_text)
        self._type_label.setObjectName(tag_obj)

        # 时长/图片数
        duration = self._result.get("duration")
        image_count = self._result.get("image_count")
        if duration:
            self._duration.setText(duration)
        elif image_count:
            self._duration.setText(f"{image_count}张图")
        else:
            self._duration.setText("")

        # 缩略图异步加载
        cover_url = self._result.get("cover_url", "")
        if cover_url:
            self._thumb_loader = ThumbnailLoader(self)
            self._thumb_loader.loaded.connect(self._on_thumb_loaded)
            self._thumb_loader.load(cover_url, (48, 48))

    def _on_thumb_loaded(self, pixmap) -> None:
        """缩略图加载完成。"""
        from PySide6.QtGui import QPixmap

        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self._thumb.setPixmap(pixmap)

    @property
    def aweme_id(self) -> str:
        """返回结果项的 aweme_id。"""
        return self._result.get("aweme_id", "")

    @property
    def result_data(self) -> dict:
        """返回结果项的完整 dict（v0.1.4）。

        供 FetchPage 在下载入队时构造 ``download_requested`` 信号载荷，
        包含 aweme_id/title/author/type/duration/image_count/cover_url。
        """
        return self._result

    def is_selected(self) -> bool:
        """返回勾选状态。"""
        return self._chk.isChecked()

    def set_selected(self, selected: bool) -> None:
        """设置勾选状态（供全选用）。

        Args:
            selected: 是否选中。
        """
        self._chk.setChecked(selected)


class PreviewItemWidget(QWidget):
    """预览结果行组件（v0.1.7）。

    与 ``ResultItemWidget`` 区别：图集类型可展开显示所有图片缩略图，
    支持图片级勾选；视频/长视频类型行为与 ``ResultItemWidget`` 一致。

    水平排列::

        [整体勾选] [缩略图 48x48] [标题] [作者] [类型] [时长/N张图] [展开按钮（图集）]

    图集展开后::

        [图片勾选 + 缩略图 48x48] × N（网格布局）

    信号:
        selection_changed: 整体勾选状态变化，传 is_selected。
    """

    selection_changed = Signal(bool)

    # 图集展开后每行的图片缩略图数量
    _IMAGES_PER_ROW = 6

    def __init__(self, result: dict, parent: QWidget | None = None) -> None:
        """初始化预览结果行。

        Args:
            result: 预览结果 dict，含 aweme_id/title/author/type/duration/
                image_count/cover_url/image_urls/video_url/author_sec_id
                等字段（来自 ``PreviewItem.to_result_dict``）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._result = result
        self._thumb_loader: ThumbnailLoader | None = None
        # 图片级勾选状态：图集类型下，每张图对应的 ThumbnailLoader 与勾选框
        self._image_thumb_loaders: list[ThumbnailLoader] = []
        self._image_chks: list[QCheckBox] = []
        # 防递归标志位：set_selected 同步图片勾选时不触发 selection_changed
        self._syncing: bool = False
        # 图集展开状态标志位（避免依赖 isVisible() 在 widget 未 show 时不可靠）
        self._expanded: bool = False
        self._setup_ui()
        self._fill_data()

    def _setup_ui(self) -> None:
        """构建行布局。"""
        self.setFixedHeight(56)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 主行
        main_row = QWidget()
        main_layout = QHBoxLayout(main_row)
        main_layout.setContentsMargins(12, 6, 12, 6)
        main_layout.setSpacing(12)

        # 整体勾选框
        self._chk = QCheckBox()
        self._chk.toggled.connect(self._on_chk_toggled)
        main_layout.addWidget(self._chk)

        # 封面缩略图
        self._thumb = QLabel()
        self._thumb.setFixedSize(48, 48)
        self._thumb.setScaledContents(True)
        self._thumb.setStyleSheet("background-color: #E5E7EB; border-radius: 4px;")
        main_layout.addWidget(self._thumb)

        # 标题
        self._title = QLabel()
        self._title.setStyleSheet("font-size: 14px; font-weight: 500;")
        self._title.setMinimumWidth(200)
        main_layout.addWidget(self._title, 1)

        # 作者
        self._author = QLabel()
        self._author.setStyleSheet("color: #6B7280; font-size: 12px;")
        main_layout.addWidget(self._author)

        # 类型标签
        self._type_label = QLabel()
        self._type_label.setStyleSheet("padding: 2px 8px; border-radius: 4px; font-size: 12px;")
        main_layout.addWidget(self._type_label)

        # 时长/图片数
        self._duration = QLabel()
        self._duration.setStyleSheet("color: #6B7280; font-size: 12px;")
        main_layout.addWidget(self._duration)

        # 展开按钮（仅图集类型显示）
        self._expand_btn = QPushButton("展开")
        self._expand_btn.setObjectName("linkBtn")
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setFlat(True)
        self._expand_btn.clicked.connect(self._on_expand_toggled)
        self._expand_btn.setVisible(False)
        main_layout.addWidget(self._expand_btn)

        layout.addWidget(main_row)

        # 图片网格容器（图集展开时显示，默认隐藏）
        self._images_widget = QWidget()
        self._images_widget.setVisible(False)
        self._images_layout = QGridLayout(self._images_widget)
        self._images_layout.setContentsMargins(60, 4, 12, 8)
        self._images_layout.setSpacing(8)
        layout.addWidget(self._images_widget)

    def _fill_data(self) -> None:
        """填充数据到各控件。"""
        self._title.setText(self._result.get("title", "") or "未命名")
        self._author.setText(self._result.get("author", "") or "")

        # 类型标签
        item_type = self._result.get("type", "video")
        tag_text, tag_obj = _TYPE_TAG_MAP.get(item_type, ("视频", "tagVideo"))
        self._type_label.setText(tag_text)
        self._type_label.setObjectName(tag_obj)

        # 时长/图片数
        duration = self._result.get("duration")
        image_count = self._result.get("image_count")
        if duration:
            self._duration.setText(duration)
        elif image_count:
            self._duration.setText(f"{image_count}张图")
        else:
            self._duration.setText("")

        # 封面缩略图异步加载
        cover_url = self._result.get("cover_url", "")
        if cover_url:
            self._thumb_loader = ThumbnailLoader(self)
            self._thumb_loader.loaded.connect(self._on_thumb_loaded)
            self._thumb_loader.load(cover_url, (48, 48))

        # 图集类型：构建图片网格 + 显示展开按钮
        image_urls = self._result.get("image_urls") or []
        if item_type == "image_set" and image_urls:
            self._expand_btn.setVisible(True)
            self._build_image_grid(image_urls)
            # 图集默认整体勾选（即所有图片勾选）
            self._chk.setChecked(True)

    def _build_image_grid(self, image_urls: list[str]) -> None:
        """构建图片网格（每张图含勾选框 + 缩略图）。

        Args:
            image_urls: 图片直链列表
        """
        for i, url in enumerate(image_urls):
            chk = QCheckBox()
            chk.setChecked(True)  # 默认全选
            chk.toggled.connect(self._on_image_chk_toggled)
            row = i // self._IMAGES_PER_ROW
            col = (i % self._IMAGES_PER_ROW) * 2
            self._images_layout.addWidget(chk, row, col)

            thumb = QLabel()
            thumb.setFixedSize(48, 48)
            thumb.setScaledContents(True)
            thumb.setStyleSheet("background-color: #E5E7EB; border-radius: 4px;")
            self._images_layout.addWidget(thumb, row, col + 1)

            loader = ThumbnailLoader(self)
            loader.loaded.connect(lambda pm, t=thumb: self._on_image_thumb_loaded(pm, t))
            loader.load(url, (48, 48))
            self._image_thumb_loaders.append(loader)
            self._image_chks.append(chk)

    def _on_thumb_loaded(self, pixmap) -> None:
        """封面缩略图加载完成。"""
        from PySide6.QtGui import QPixmap

        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self._thumb.setPixmap(pixmap)

    def _on_image_thumb_loaded(self, pixmap, thumb: QLabel) -> None:
        """图片缩略图加载完成。"""
        from PySide6.QtGui import QPixmap

        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            thumb.setPixmap(pixmap)

    def _on_chk_toggled(self, checked: bool) -> None:
        """整体勾选框状态变化。

        图集类型：同步所有图片勾选框；视频类型：仅自身。
        """
        if self._syncing:
            return
        self._syncing = True
        try:
            for chk in self._image_chks:
                chk.setChecked(checked)
        finally:
            self._syncing = False
        self.selection_changed.emit(checked)

    def _on_image_chk_toggled(self, _checked: bool) -> None:
        """图片勾选框状态变化：同步整体勾选框。

        图集类型：至少一张图勾选则整体勾选；全不选则取消。
        """
        if self._syncing:
            return
        any_selected = any(chk.isChecked() for chk in self._image_chks)
        self._syncing = True
        try:
            self._chk.setChecked(any_selected)
        finally:
            self._syncing = False
        self.selection_changed.emit(any_selected)

    def _on_expand_toggled(self) -> None:
        """展开按钮点击：切换图片网格显示。"""
        # 用显式 _expanded 标志位判断状态，避免依赖 isVisible()
        # （widget 未 show 时 isVisible() 总是 False，会导致二次点击无法收起）
        self._expanded = not self._expanded
        self._images_widget.setVisible(self._expanded)
        self._expand_btn.setText("收起" if self._expanded else "展开")
        # 展开/收起后调整整体高度
        if self._expanded:
            # 展开时取消固定高度限制
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(56)
        else:
            self.setFixedHeight(56)

    @property
    def aweme_id(self) -> str:
        """返回结果项的 aweme_id。"""
        return self._result.get("aweme_id", "")

    @property
    def result_data(self) -> dict:
        """返回结果项的完整 dict（含图片级勾选状态）。

        v0.1.7：图集类型额外携带 ``selected_image_indices`` 字段，
        值为勾选图片索引的 JSON 数组字符串（如 ``"[0,1,3]"``）；
        空字符串表示全选（与 DB schema 一致）。
        """
        data = dict(self._result)
        data["selected_image_indices"] = self.get_selected_image_indices_str()
        return data

    def is_selected(self) -> bool:
        """返回整体勾选状态。

        图集类型：至少一张图勾选则为 True；视频类型：勾选框状态。
        """
        if self._image_chks:
            return any(chk.isChecked() for chk in self._image_chks)
        return self._chk.isChecked()

    def set_selected(self, selected: bool) -> None:
        """设置勾选状态（供全选用）。

        图集类型：同步所有图片勾选框；视频类型：仅设置整体勾选框。

        Args:
            selected: 是否选中。
        """
        self._syncing = True
        try:
            self._chk.setChecked(selected)
            for chk in self._image_chks:
                chk.setChecked(selected)
        finally:
            self._syncing = False

    def get_selected_image_indices(self) -> list[int]:
        """返回勾选的图片索引列表。

        图集类型：返回勾选图片的索引；视频类型：返回空列表。
        空列表与"全选"在 ``selected_image_indices`` 字段中都用空字符串表示，
        但本方法仅返回勾选索引，由调用方决定序列化方式。
        """
        return [i for i, chk in enumerate(self._image_chks) if chk.isChecked()]

    def get_selected_image_indices_str(self) -> str:
        """返回勾选图片索引的 JSON 数组字符串。

        - 视频类型：返回空字符串（表示全选/不适用）
        - 图集类型全选：返回空字符串（与 DB schema 约定一致，空表示全选）
        - 图集类型部分选：返回 ``"[0,1,3]"`` 格式
        """
        if not self._image_chks:
            return ""
        indices = self.get_selected_image_indices()
        total = len(self._image_chks)
        # 全选时用空字符串表示，节省存储且与 DB schema 约定一致
        if len(indices) == total:
            return ""
        import json

        return json.dumps(indices)


class FetchPage(QWidget):
    """链接抓取页。

    信号:
        parse_requested: 点击"开始解析"，传输入框文本。
        home_fetch_requested: 点击过滤栏"开始抓取"，传 sec_user_id 与 filters。
        download_requested: 点击"开始下载"，传选中的结果项 dict 列表。
            v0.1.3：下载目录不再由抓取页传入，由 Bridge 从设置页配置读取。
            v0.1.4：信号载荷从 ``list[str]``（aweme_id）改为 ``list[dict]``，
            每项含 aweme_id/title/author/type/duration/image_count/cover_url，
            供 Bridge 在创建 TaskItem 时直接写入 title/cover_url（用户反馈 #2/#3）。
        cancel_parse_requested: 取消解析。
        cancel_home_fetch_requested: 取消主页抓取。
    """

    parse_requested = Signal(str)
    home_fetch_requested = Signal(str, dict)
    download_requested = Signal(list)
    cancel_parse_requested = Signal()
    cancel_home_fetch_requested = Signal()

    def __init__(
        self,
        crawler_bridge: CrawlerBridge,
        conn: sqlite3.Connection,
        parent: QWidget | None = None,
    ) -> None:
        """初始化链接抓取页。

        Args:
            crawler_bridge: 爬虫层桥接器。
            conn: 数据库连接（保留供未来扩展，v0.1.3 起本页不再读取下载目录）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._bridge = crawler_bridge
        self._conn = conn
        # v0.1.7：列表可容纳 ResultItemWidget（主页抓取流程）与 PreviewItemWidget（链接预览流程）
        self._result_widgets: list[ResultItemWidget | PreviewItemWidget] = []
        self._is_parsing = False
        self._is_fetching = False
        self._loading_overlay = LoadingOverlay(self)
        # v0.1.6：全选联动防递归标志位（用户反馈 #4）
        # 单项勾选同步全选 / 全选同步单项时置 True，避免 stateChanged 信号递归触发
        self._syncing_select_all: bool = False

        self._setup_ui()
        self._connect_bridge_signals()

    def _setup_ui(self) -> None:
        """构建页面布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题区
        title_label = QLabel("链接抓取")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # 内容区
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 8, 24, 8)
        content_layout.setSpacing(8)

        # 输入区
        input_layout = QHBoxLayout()
        self._input_edit = QPlainTextEdit()
        self._input_edit.setFixedHeight(120)
        self._input_edit.setPlaceholderText(
            "在此粘贴抖音链接，每行一个\n支持视频链接、图文链接、用户主页链接"
        )
        input_layout.addWidget(self._input_edit, 1)

        # 导入文件按钮
        import_btn = QPushButton("导入文件")
        import_btn.clicked.connect(self._on_import_file)
        input_layout.addWidget(import_btn, alignment=Qt.AlignmentFlag.AlignTop)
        content_layout.addLayout(input_layout)

        # 错误提示
        self._input_error_label = QLabel()
        self._input_error_label.setObjectName("errorText")
        self._input_error_label.setVisible(False)
        content_layout.addWidget(self._input_error_label)

        # 操作行：开始解析 + 弹性间距 + 开始下载（v0.1.2：开始下载按钮移位至操作行右侧，
        # 距右边界 24px，符合用户反馈 #10）
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 24, 0)
        self._parse_btn = QPushButton("开始解析")
        self._parse_btn.setObjectName("primaryBtn")
        self._parse_btn.clicked.connect(self._on_parse_clicked)
        action_layout.addWidget(self._parse_btn)
        action_layout.addStretch(1)
        self._download_btn = QPushButton("开始下载 (0)")
        self._download_btn.setObjectName("primaryBtn")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download_clicked)
        action_layout.addWidget(self._download_btn)
        content_layout.addLayout(action_layout)

        # 主页提示行
        self._home_hint_label = QLabel("⚠ 检测到用户主页链接，已展开过滤栏")
        self._home_hint_label.setStyleSheet("color: #F59E0B; font-size: 13px;")
        self._home_hint_label.setVisible(False)
        content_layout.addWidget(self._home_hint_label)

        # 过滤栏（默认隐藏）
        self._filter_bar = FilterBar()
        self._filter_bar.fetch_requested.connect(self._on_fetch_requested)
        self._filter_bar.setVisible(False)
        content_layout.addWidget(self._filter_bar)

        # 列表头
        list_header = QHBoxLayout()
        self._select_all_chk = QCheckBox("全选")
        # v0.1.6：启用三态复选框（用户反馈 #4）
        # Qt.Unchecked=0 项勾选 / Qt.PartiallyChecked=1~N-1 项 / Qt.Checked=N 项
        self._select_all_chk.setTristate(True)
        # stateChanged(int) 携带 Qt.CheckState 三态值，toggled(bool) 仅两态不够用
        self._select_all_chk.stateChanged.connect(self._on_select_all_state_changed)
        list_header.addWidget(self._select_all_chk)
        self._selected_count_label = QLabel("已选 0 / 共 0 项")
        self._selected_count_label.setStyleSheet("color: #6B7280; font-size: 13px;")
        list_header.addWidget(self._selected_count_label)
        list_header.addStretch(1)
        content_layout.addLayout(list_header)

        # 结果列表
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setVisible(False)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch(1)
        self._scroll_area.setWidget(self._list_container)
        content_layout.addWidget(self._scroll_area, 1)

        # 空状态
        self._empty_widget = self._create_empty_widget()
        content_layout.addWidget(self._empty_widget)

        layout.addWidget(content, 1)

    def _create_empty_widget(self) -> QWidget:
        """创建空状态 widget。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        label = QLabel("没有解析到结果")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        layout.addWidget(label)
        hint = QLabel("请检查链接是否正确")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(hint)
        widget.setVisible(False)
        return widget

    def _connect_bridge_signals(self) -> None:
        """连接 Bridge 的 WorkerSignals。"""
        signals = self._bridge._worker_signals  # noqa: SLF001
        signals.parse_progress.connect(self._on_parse_progress)
        signals.parse_completed.connect(self.on_parse_completed)
        signals.parse_failed.connect(self.on_parse_failed)
        # v0.1.7：预览解析（含图片直链）
        signals.preview_completed.connect(self.on_preview_completed)
        signals.preview_failed.connect(self.on_preview_failed)
        signals.home_fetch_progress.connect(self.on_home_fetch_progress)
        signals.home_fetch_completed.connect(self.on_home_fetch_completed)
        signals.home_fetch_failed.connect(self.on_home_fetch_failed)

    def refresh(self) -> None:
        """刷新页面。

        v0.1.3：抓取页不再持有下载目录控件，本方法为空实现保留以符合
        ``Page`` 接口约定（``BridgeConnections`` 与 ``MainWindow`` 在
        页面切换等时机统一调用各页 ``refresh()``）。
        """
        return

    def _on_import_file(self) -> None:
        """导入文件按钮点击。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择链接文件", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                from pathlib import Path

                content = Path(file_path).read_text(encoding="utf-8")
                current = self._input_edit.toPlainText()
                if current:
                    self._input_edit.setPlainText(current + "\n" + content)
                else:
                    self._input_edit.setPlainText(content)
            except OSError as e:
                self._show_input_error(f"文件读取失败：{e}")

    def _on_parse_clicked(self) -> None:
        """开始解析按钮点击。

        v0.1.6：解析中点击按钮取消解析时，保留输入框文本（供用户编辑后重试），
        清空已解析的部分结果、重置全选状态、隐藏过滤栏（用户反馈 #5）。
        """
        if self._is_parsing:
            # 取消解析：保留输入文本，清空部分结果
            self._is_parsing = False
            self._parse_btn.setText("开始解析")
            self._loading_overlay.hide()
            self.cancel_parse_requested.emit()
            # v0.1.6：清理部分结果 + 重置全选 + 隐藏过滤栏
            self._clear_results()
            self._home_hint_label.setVisible(False)
            self._filter_bar.setVisible(False)
            self._syncing_select_all = True
            try:
                self._select_all_chk.setCheckState(Qt.CheckState.Unchecked)
            finally:
                self._syncing_select_all = False
            self._update_result_visibility()
            self._update_selected_count()
            Toast.show_info(self, "已取消解析")
            return

        text = self._input_edit.toPlainText().strip()
        if not text:
            self._show_input_error("请输入链接")
            return

        self._hide_input_error()
        self._is_parsing = True
        self._parse_btn.setText("解析中... 点击取消")
        self._loading_overlay.show(self, "正在解析链接...", cancelable=True)
        self.parse_requested.emit(text)

    def _on_parse_progress(self, current: int, total: int) -> None:
        """解析进度。"""
        self._parse_btn.setText(f"解析中... {current}/{total}")
        self._loading_overlay.update_progress(current, total)

    def on_parse_completed(self, results: list) -> None:
        """解析完成。

        Args:
            results: ParsedURL 列表。
        """
        self._is_parsing = False
        self._parse_btn.setText("开始解析")
        self._loading_overlay.hide()
        self._clear_results()

        has_home_link = False
        for result in results:
            # ParsedURL 转 dict
            result_dict = self._parsed_url_to_dict(result)
            if result_dict.get("type") == "user_home":
                has_home_link = True
                self._filter_bar.set_sec_user_id(result_dict.get("sec_user_id", ""))
            self._add_result_widget(result_dict)

        if has_home_link:
            self._home_hint_label.setVisible(True)
            self._filter_bar.setVisible(True)

        self._update_result_visibility()
        self._update_selected_count()

    def on_parse_failed(self, reason: str) -> None:
        """解析失败。"""
        self._is_parsing = False
        self._parse_btn.setText("开始解析")
        self._loading_overlay.hide()
        self._show_input_error(f"解析失败：{reason}")

    def on_preview_completed(self, items: list) -> None:
        """预览解析完成（v0.1.7）。

        与 ``on_parse_completed`` 区别：接收 ``PreviewItem`` 列表，每项含
        完整的标题/封面/类型/图片直链/视频直链，渲染为 ``PreviewItemWidget``，
        图集类型可展开预览图片并支持图片级勾选（用户反馈 #7）。

        Args:
            items: ``list[PreviewItem]``，预览解析结果
        """
        self._is_parsing = False
        self._parse_btn.setText("开始解析")
        self._loading_overlay.hide()
        self._clear_results()

        for item in items:
            self._add_preview_widget(item)

        self._update_result_visibility()
        self._update_selected_count()

    def on_preview_failed(self, reason: str) -> None:
        """预览解析失败（v0.1.7）。"""
        self._is_parsing = False
        self._parse_btn.setText("开始解析")
        self._loading_overlay.hide()
        self._show_input_error(f"解析失败：{reason}")

    def on_home_fetch_progress(self, current: int, total: int) -> None:
        """主页抓取进度。"""
        if total > 0:
            self._parse_btn.setText(f"抓取中... {current}/{total}")
        else:
            self._parse_btn.setText(f"抓取中... 已获取 {current}")
            self._loading_overlay.update_message(f"已获取 {current} 条")

    def on_home_fetch_completed(self, results: list) -> None:
        """主页抓取完成。"""
        self._is_fetching = False
        self._parse_btn.setText("开始解析")
        self._filter_bar.set_loading(False)
        self._loading_overlay.hide()
        self._clear_results()

        for post_item in results:
            result_dict = self._post_item_to_dict(post_item)
            self._add_result_widget(result_dict)

        self._update_result_visibility()
        self._update_selected_count()

    def on_home_fetch_failed(self, reason: str) -> None:
        """主页抓取失败。"""
        self._is_fetching = False
        self._parse_btn.setText("开始解析")
        self._filter_bar.set_loading(False)
        self._loading_overlay.hide()
        self._show_input_error(f"主页抓取失败：{reason}")

    def _on_fetch_requested(self, filters: dict) -> None:
        """过滤栏开始抓取。"""
        sec_user_id = filters.get("sec_user_id", "")
        if not sec_user_id:
            return
        self._is_fetching = True
        self._filter_bar.set_loading(True)
        self._loading_overlay.show(self, "正在抓取用户主页...", cancelable=True)
        self.home_fetch_requested.emit(sec_user_id, filters)

    def _parsed_url_to_dict(self, parsed) -> dict:
        """ParsedURL 对象转 dict。"""
        return {
            "aweme_id": getattr(parsed, "aweme_id", None) or "",
            "title": "抖音链接",
            "author": "",
            "type": getattr(parsed, "type", "video"),
            "duration": None,
            "image_count": None,
            "cover_url": "",
            "sec_user_id": getattr(parsed, "sec_user_id", None) or "",
            "url": getattr(parsed, "url", ""),
        }

    def _post_item_to_dict(self, post) -> dict:
        """PostItem 对象转 dict。"""
        return {
            "aweme_id": getattr(post, "aweme_id", ""),
            "title": getattr(post, "title", ""),
            "author": getattr(post, "author", ""),
            "type": getattr(post, "type", "video"),
            "duration": getattr(post, "duration", None),
            "image_count": getattr(post, "image_count", None),
            "cover_url": getattr(post, "cover_url", ""),
        }

    def _add_result_widget(self, result: dict) -> ResultItemWidget:
        """添加结果行到列表。"""
        widget = ResultItemWidget(result)
        # v0.1.6：单项勾选变化时同步全选复选框三态（用户反馈 #4）
        widget.selection_changed.connect(self._on_item_selection_changed)
        count = self._list_layout.count()
        self._list_layout.insertWidget(count - 1, widget)
        self._result_widgets.append(widget)
        return widget

    def _add_preview_widget(self, item: PreviewItem) -> PreviewItemWidget:
        """添加预览结果行到列表（v0.1.7）。

        与 ``_add_result_widget`` 区别：接收 ``PreviewItem``，渲染为
        ``PreviewItemWidget``（支持图集展开与图片级勾选）。
        """
        widget = PreviewItemWidget(item.to_result_dict())
        widget.selection_changed.connect(self._on_item_selection_changed)
        count = self._list_layout.count()
        self._list_layout.insertWidget(count - 1, widget)
        self._result_widgets.append(widget)
        return widget

    def _clear_results(self) -> None:
        """清空结果列表。"""
        for widget in self._result_widgets:
            widget.deleteLater()
        self._result_widgets.clear()

    def _update_result_visibility(self) -> None:
        """根据结果数量切换空状态与列表显示。"""
        has_results = len(self._result_widgets) > 0
        self._scroll_area.setVisible(has_results)
        self._empty_widget.setVisible(not has_results)
        if not has_results:
            self._empty_widget.setVisible(True)

    def _on_select_all_state_changed(self, state: int) -> None:
        """全选复选框状态变化时，同步所有结果项勾选状态。

        v0.1.6：三态复选框联动（用户反馈 #4）。
        - ``Qt.Unchecked`` / ``Qt.Checked``：同步所有项为取消/勾选
        - ``Qt.PartiallyChecked``：不响应（避免点击部分选状态时循环触发）
        - ``_syncing_select_all`` 标志位防止单项→全选→单项的递归触发

        Args:
            state: ``Qt.CheckState`` 枚举值（0=Unchecked, 1=PartiallyChecked, 2=Checked）。
        """
        if self._syncing_select_all:
            return
        if state == Qt.CheckState.PartiallyChecked.value:
            # 部分选状态不响应点击（避免循环）
            return
        selected = state == Qt.CheckState.Checked.value
        self._syncing_select_all = True
        try:
            for widget in self._result_widgets:
                widget.set_selected(selected)
        finally:
            self._syncing_select_all = False
        self._update_selected_count()

    def _on_item_selection_changed(self, _is_selected: bool) -> None:
        """单项结果勾选状态变化时，同步全选复选框三态。

        v0.1.6：手动勾选全部 N 项时全选自动变为已勾选；取消任一项时变为部分选；
        取消全部时变为未选（用户反馈 #4）。使用 ``_syncing_select_all`` 标志位
        防止 ``setCheckState`` 触发 ``stateChanged`` 信号导致递归。

        Args:
            _is_selected: 单项勾选状态（未使用，仅作信号签名匹配）。
        """
        if self._syncing_select_all:
            return
        selected_count = sum(1 for w in self._result_widgets if w.is_selected())
        total_count = len(self._result_widgets)
        if total_count == 0 or selected_count == 0:
            new_state = Qt.CheckState.Unchecked
        elif selected_count == total_count:
            new_state = Qt.CheckState.Checked
        else:
            new_state = Qt.CheckState.PartiallyChecked
        self._syncing_select_all = True
        try:
            self._select_all_chk.setCheckState(new_state)
        finally:
            self._syncing_select_all = False
        self._update_selected_count()

    def _update_selected_count(self) -> None:
        """更新已选计数与下载按钮。"""
        total = len(self._result_widgets)
        selected = sum(1 for w in self._result_widgets if w.is_selected())
        self._selected_count_label.setText(f"已选 {selected} / 共 {total} 项")
        self._download_btn.setText(f"开始下载 ({selected})")
        self._download_btn.setEnabled(selected > 0)

    def _on_download_clicked(self) -> None:
        """开始下载按钮点击。

        v0.1.3：下载目录不再由抓取页传入，``download_requested`` 仅传结果项 dict。
        下载目录为空校验由 ``BridgeConnections._on_download_requested`` 负责，
        从设置页配置读取；为空时弹窗提示"请先在设置页配置下载目录"。

        v0.1.4：信号载荷从 ``list[str]``（aweme_id）改为 ``list[dict]``，
        每项含 aweme_id/title/author/type/duration/image_count/cover_url，
        供 Bridge 在创建 TaskItem 时直接写入 title/cover_url，
        让下载页能立即显示视频标题与封面，无需等待解析直链回填。

        v0.1.6：点击下载时仅 emit 信号 + Toast 提示，**不立即清理**抓取页内容。
        清理在 ``DownloadBridge.download_started`` 信号到达后由
        ``clear_after_download_started`` 执行，避免提前清理导致任务丢失
        （用户反馈 #6）。
        """
        items = [w.result_data for w in self._result_widgets if w.is_selected()]
        if items:
            self.download_requested.emit(items)
            Toast.show_success(self, f"已加入下载队列（{len(items)} 项）")

    def clear_after_download_started(self) -> None:
        """Bridge 确认入队成功后清理抓取页内容。

        v0.1.6：在 ``DownloadBridge.download_started`` 信号到达后由
        ``BridgeConnections._on_download_started`` 调用（用户反馈 #6）。

        清理内容：
            1. 输入框文本
            2. 结果列表（删除所有 ResultItemWidget）
            3. 主页提示行 + 过滤栏（隐藏）
            4. 全选复选框状态（重置为未选）
            5. 已选计数与下载按钮（重置为 0）

        若入队失败（``download_started`` 未到达），抓取页内容保留供用户重试。
        """
        # 1. 清空输入框
        self._input_edit.clear()
        # 2. 清空结果列表
        self._clear_results()
        # 3. 隐藏主页提示行 + 过滤栏
        self._home_hint_label.setVisible(False)
        self._filter_bar.setVisible(False)
        # 4. 重置全选状态（_syncing_select_all 防止递归触发 _on_select_all_state_changed）
        self._syncing_select_all = True
        try:
            self._select_all_chk.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._syncing_select_all = False
        # 5. 切换空状态显示 + 重置计数
        self._update_result_visibility()
        self._update_selected_count()
        # 6. 隐藏输入错误提示（若有）
        self._hide_input_error()
        logger.info("抓取页已在入队成功后清理")

    def _show_input_error(self, message: str) -> None:
        """显示输入错误提示。"""
        self._input_error_label.setText(message)
        self._input_error_label.setVisible(True)
        self._input_edit.setStyleSheet("border: 1px solid #EF4444;")

    def _hide_input_error(self) -> None:
        """隐藏输入错误提示。"""
        self._input_error_label.setVisible(False)
        self._input_edit.setStyleSheet("")
