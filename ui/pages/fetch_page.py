"""链接抓取页模块。

实现链接抓取页，包含多行链接输入、文件导入、解析、解析结果列表、
主页过滤栏、勾选下载全流程。

严格遵循设计文档 3.1 节页面 2 与 UIUX 规范 5.3 节。

布局结构::

    [56px 标题区: "链接抓取"]
    [输入区: QPlainTextEdit(120px) + 导入文件按钮]
    [操作行: 开始解析按钮]
    [提示行（检测到主页链接时）]
    [过滤栏（主页链接时显示）]
    [列表头: 全选 + 已选计数]
    [解析结果列表 QScrollArea]
    [56px 底部操作栏: 下载目录 + 浏览 + 开始下载(N)]
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.logger import get_logger
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

    def is_selected(self) -> bool:
        """返回勾选状态。"""
        return self._chk.isChecked()

    def set_selected(self, selected: bool) -> None:
        """设置勾选状态（供全选用）。

        Args:
            selected: 是否选中。
        """
        self._chk.setChecked(selected)


class FetchPage(QWidget):
    """链接抓取页。

    信号:
        parse_requested: 点击"开始解析"，传输入框文本。
        home_fetch_requested: 点击过滤栏"开始抓取"，传 sec_user_id 与 filters。
        download_requested: 点击"开始下载"，传选中的 aweme_id 列表与下载目录。
        cancel_parse_requested: 取消解析。
        cancel_home_fetch_requested: 取消主页抓取。
    """

    parse_requested = Signal(str)
    home_fetch_requested = Signal(str, dict)
    download_requested = Signal(list, str)
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
            conn: 数据库连接（读取默认下载目录）。
            parent: 父控件。
        """
        super().__init__(parent)
        self._bridge = crawler_bridge
        self._conn = conn
        self._result_widgets: list[ResultItemWidget] = []
        self._is_parsing = False
        self._is_fetching = False
        self._loading_overlay = LoadingOverlay(self)

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

        # 操作行
        action_layout = QHBoxLayout()
        self._parse_btn = QPushButton("开始解析")
        self._parse_btn.setObjectName("primaryBtn")
        self._parse_btn.clicked.connect(self._on_parse_clicked)
        action_layout.addWidget(self._parse_btn)
        action_layout.addStretch(1)
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
        self._select_all_chk.toggled.connect(self._on_select_all)
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

        # 底部操作栏
        bottom = QWidget()
        bottom.setFixedHeight(56)
        bottom.setStyleSheet("border-top: 1px solid #E5E7EB;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(24, 8, 24, 8)
        bottom_layout.setSpacing(12)

        bottom_layout.addWidget(QLabel("下载目录:"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择下载目录...")
        bottom_layout.addWidget(self._dir_edit, 1)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._on_browse_dir)
        bottom_layout.addWidget(browse_btn)

        self._download_btn = QPushButton("开始下载 (0)")
        self._download_btn.setObjectName("primaryBtn")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download_clicked)
        bottom_layout.addWidget(self._download_btn)

        layout.addWidget(bottom)

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
        signals.home_fetch_progress.connect(self.on_home_fetch_progress)
        signals.home_fetch_completed.connect(self.on_home_fetch_completed)
        signals.home_fetch_failed.connect(self.on_home_fetch_failed)

    def refresh(self) -> None:
        """刷新页面（从 DB 读取默认下载目录）。"""
        from app.repositories import ConfigRepository

        config_repo = ConfigRepository(self._conn)
        download_dir = config_repo.get("download_dir")
        if isinstance(download_dir, str) and download_dir and not self._dir_edit.text():
            self._dir_edit.setText(download_dir)

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
        """开始解析按钮点击。"""
        if self._is_parsing:
            # 取消解析
            self._is_parsing = False
            self._parse_btn.setText("开始解析")
            self._loading_overlay.hide()
            self.cancel_parse_requested.emit()
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
        widget.selection_changed.connect(self._update_selected_count)
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

    def _on_select_all(self, checked: bool) -> None:
        """全选/取消全选。"""
        for widget in self._result_widgets:
            widget.set_selected(checked)

    def _update_selected_count(self) -> None:
        """更新已选计数与下载按钮。"""
        total = len(self._result_widgets)
        selected = sum(1 for w in self._result_widgets if w.is_selected())
        self._selected_count_label.setText(f"已选 {selected} / 共 {total} 项")
        self._download_btn.setText(f"开始下载 ({selected})")
        self._download_btn.setEnabled(selected > 0)

    def _on_browse_dir(self) -> None:
        """浏览下载目录。"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if dir_path:
            self._dir_edit.setText(dir_path)

    def _on_download_clicked(self) -> None:
        """开始下载按钮点击。"""
        dir_path = self._dir_edit.text().strip()
        if not dir_path:
            self._dir_edit.setStyleSheet("border: 1px solid #EF4444;")
            return
        self._dir_edit.setStyleSheet("")

        aweme_ids = [w.aweme_id for w in self._result_widgets if w.is_selected()]
        if aweme_ids:
            self.download_requested.emit(aweme_ids, dir_path)
            Toast.show_success(self, f"已加入下载队列（{len(aweme_ids)} 项）")

    def _show_input_error(self, message: str) -> None:
        """显示输入错误提示。"""
        self._input_error_label.setText(message)
        self._input_error_label.setVisible(True)
        self._input_edit.setStyleSheet("border: 1px solid #EF4444;")

    def _hide_input_error(self) -> None:
        """隐藏输入错误提示。"""
        self._input_error_label.setVisible(False)
        self._input_edit.setStyleSheet("")
