"""Cookie 配置页占位模块。

v0.0.7 仅提供标题 + 空白内容区占位，具体功能（Cookie 池列表、
添加/测试/删除、教程）在 v0.0.8 实现。

严格遵循设计文档 3.1 节与 v0.0.7 计划文档任务 5。
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from worker.crawler_bridge import CrawlerBridge


class CookiePage(QWidget):
    """Cookie 配置页占位骨架。

    v0.0.7 仅显示标题与提示文字，存储 CrawlerBridge 引用供 v0.0.8 使用。
    """

    def __init__(
        self,
        crawler_bridge: CrawlerBridge,
        conn: sqlite3.Connection,
        parent: QWidget | None = None,
    ) -> None:
        """初始化 Cookie 配置页。

        Args:
            crawler_bridge: 爬虫层桥接器，供 v0.0.8 实现具体功能。
            conn: 数据库连接，供 v0.0.8 读取 Cookie 列表。
            parent: 父控件。
        """
        super().__init__(parent)
        self._crawler_bridge = crawler_bridge
        self._conn = conn
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建占位布局：标题 + 居中提示。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_label = QLabel("Cookie 配置")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        placeholder = QLabel("Cookie 配置页 — 待 v0.0.8 实现")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        layout.addWidget(placeholder, 1)

    def refresh(self) -> None:
        """刷新页面数据（占位空实现，v0.0.8 填充具体刷新逻辑）。"""
