"""Bridge 连接层模块。

将 MainWindow 与 ``DownloadBridge`` / ``CrawlerBridge`` 的信号连接到
UI 槽函数，并将页面信号转发到 Bridge 控制信号，建立 UI 与工作线程之间的
信号/槽粘合层。

严格遵循设计文档第 2.3 节（线程模型）与 v0.0.8 计划文档任务 8。

职责边界：
    - 页面已自行连接 Bridge 的 WorkerSignals（接收更新）
    - 本模块负责连接页面信号 → Bridge ControlSignals（发起控制）
    - 处理跨页面交互（导航、Cookie 失效提示等）
    - 处理 download_requested：创建 Task/TaskItem 后启动下载

信号连接表::

    页面信号 → Bridge ControlSignals:
        DownloadPage.pause_item(int)      → download_bridge.pause_download
        DownloadPage.resume_item(int)     → download_bridge.resume_download
        DownloadPage.retry_item(int)      → download_bridge.start_download([id])
        DownloadPage.pause_all_clicked()  → download_bridge.pause_all
        DownloadPage.resume_all_clicked() → download_bridge.resume_all
        FetchPage.parse_requested(str)             → crawler_bridge.start_parse
        FetchPage.home_fetch_requested(str,dict)   → crawler_bridge.start_home_fetch
        FetchPage.cancel_parse_requested()         → crawler_bridge.cancel_parse
        FetchPage.cancel_home_fetch_requested()    → crawler_bridge.cancel_home_fetch
        CookiePage.test_cookie_requested(int)      → crawler_bridge.test_cookie
        CookiePage.test_all_cookies_requested()    → crawler_bridge.test_all_cookies

    页面信号 → 本地处理:
        DownloadPage.clear_completed_clicked() → 删除 DB 中已完成任务项
        DownloadPage.navigate_to_fetch()       → 切换到链接抓取页
        FetchPage.download_requested(list,str) → 创建 Task/TaskItem + 启动下载
        CookiePage.add_cookie_requested(str,str)  → CookieRepository.add
        CookiePage.remove_cookie_requested(int)   → CookieRepository.remove
        SettingsPage.export_logs_requested()      → 打开日志目录

    Bridge WorkerSignals → 本地处理（页面未处理的信号）:
        DownloadBridge.cookie_invalid(str) → 弹窗提示 + 切换到 Cookie 页
        DownloadBridge.task_completed(int) → 刷新下载页状态栏
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from app.logger import get_logger
from app.models import Cookie, Task, TaskItem
from app.repositories import (
    CookieRepository,
    TaskItemRepository,
    TaskRepository,
)
from worker.crawler_bridge import CrawlerBridge
from worker.download_bridge import DownloadBridge

if TYPE_CHECKING:
    from ui.main_window import MainWindow

logger = get_logger(__name__)


class BridgeConnections:
    """Bridge 信号连接粘合层。

    连接 DownloadBridge / CrawlerBridge 的 WorkerSignals 到 UI 槽函数，
    并将页面信号转发到 Bridge ControlSignals。

    线程安全：
        Bridge 信号通过 Qt 的 Signal 机制跨线程传递，槽函数在主线程执行，
        可安全操作 UI。
    """

    def __init__(
        self,
        main_window: MainWindow,
        download_bridge: DownloadBridge,
        crawler_bridge: CrawlerBridge,
        pages: dict[str, QWidget],
    ) -> None:
        """初始化 Bridge 连接层。

        Args:
            main_window: 主窗口实例。
            download_bridge: 下载引擎桥接器。
            crawler_bridge: 爬虫层桥接器。
            pages: 4 个页面引用字典，键为 "download"/"fetch"/"cookie"/"settings"。
        """
        self._main_window = main_window
        self._download_bridge = download_bridge
        self._crawler_bridge = crawler_bridge
        self._pages = pages

    def setup_connections(self) -> None:
        """连接所有 Bridge 信号与页面信号。"""
        self._connect_download_bridge_signals()
        self._connect_crawler_bridge_signals()
        self._connect_page_signals()
        logger.info("Bridge 信号连接已建立")

    # === Bridge WorkerSignals 连接 ===

    def _connect_download_bridge_signals(self) -> None:
        """连接 DownloadBridge 的 WorkerSignals 到槽函数。"""
        signals = self._download_bridge._worker_signals  # noqa: SLF001
        signals.cookie_invalid.connect(self._on_cookie_invalid)
        signals.task_completed.connect(self._on_task_completed)
        logger.debug("DownloadBridge 信号已连接")

    def _connect_crawler_bridge_signals(self) -> None:
        """连接 CrawlerBridge 的 WorkerSignals 到槽函数。

        页面已自行连接 parse/home_fetch/cookie_test_result 信号，
        此处无需重复连接。
        """
        logger.debug("CrawlerBridge 信号已由页面自行连接")

    # === 页面信号连接 ===

    def _connect_page_signals(self) -> None:
        """连接各页面信号到 Bridge 控制信号或本地处理槽。"""
        self._connect_download_page_signals()
        self._connect_fetch_page_signals()
        self._connect_cookie_page_signals()
        self._connect_settings_page_signals()

    def _connect_download_page_signals(self) -> None:
        """连接 DownloadPage 信号。"""
        page = self._pages.get("download")
        if page is None:
            return
        control = self._download_bridge._control_signals  # noqa: SLF001
        page.pause_item.connect(control.pause_download.emit)
        page.resume_item.connect(control.resume_download.emit)
        page.retry_item.connect(lambda tid: control.start_download.emit([tid]))
        page.pause_all_clicked.connect(control.pause_all.emit)
        page.resume_all_clicked.connect(control.resume_all.emit)
        page.clear_completed_clicked.connect(self._on_clear_completed)
        page.navigate_to_fetch.connect(lambda: self._switch_page(1))

    def _connect_fetch_page_signals(self) -> None:
        """连接 FetchPage 信号。"""
        page = self._pages.get("fetch")
        if page is None:
            return
        control = self._crawler_bridge._control_signals  # noqa: SLF001
        page.parse_requested.connect(control.start_parse.emit)
        page.home_fetch_requested.connect(control.start_home_fetch.emit)
        page.cancel_parse_requested.connect(control.cancel_parse.emit)
        page.cancel_home_fetch_requested.connect(control.cancel_home_fetch.emit)
        page.download_requested.connect(self._on_download_requested)

    def _connect_cookie_page_signals(self) -> None:
        """连接 CookiePage 信号。"""
        page = self._pages.get("cookie")
        if page is None:
            return
        control = self._crawler_bridge._control_signals  # noqa: SLF001
        page.test_cookie_requested.connect(control.test_cookie.emit)
        page.test_all_cookies_requested.connect(control.test_all_cookies.emit)
        page.add_cookie_requested.connect(self._on_add_cookie)
        page.remove_cookie_requested.connect(self._on_remove_cookie)

    def _connect_settings_page_signals(self) -> None:
        """连接 SettingsPage 信号。"""
        page = self._pages.get("settings")
        if page is None:
            return
        page.settings_changed.connect(self._on_settings_changed)
        page.export_logs_requested.connect(self._on_export_logs)

    # === DownloadBridge WorkerSignals 槽函数 ===

    def _on_cookie_invalid(self, message: str) -> None:
        """Cookie 失效通知：弹窗提示 + 切换到 Cookie 配置页。"""
        logger.warning("Cookie 失效：%s", message)
        QMessageBox.warning(
            self._main_window,
            "Cookie 失效",
            f"{message}\n\n请前往 Cookie 配置页更新 Cookie。",
            QMessageBox.StandardButton.Ok,
        )
        self._switch_page(2)

    def _on_task_completed(self, task_id: int) -> None:
        """某任务下所有子项完成：刷新下载页。"""
        logger.info("任务全部完成：task_id=%s", task_id)
        page = self._pages.get("download")
        if page is not None:
            page.refresh()

    # === DownloadPage 信号槽 ===

    def _on_clear_completed(self) -> None:
        """清空已完成任务：从 DB 删除 completed 状态的 task_items。"""
        conn = self._main_window._conn  # noqa: SLF001
        item_repo = TaskItemRepository(conn)
        completed_items = item_repo.get_by_status("completed")
        for item in completed_items:
            item_repo.delete(item.id)  # type: ignore[arg-type]
        logger.info("已清空 %d 条已完成任务", len(completed_items))

    # === FetchPage 信号槽 ===

    def _on_download_requested(self, aweme_ids: list, download_dir: str) -> None:
        """开始下载：创建 Task/TaskItem，提交到下载队列。

        Args:
            aweme_ids: 待下载的 aweme_id 列表。
            download_dir: 下载目录。
        """
        if not aweme_ids:
            return

        conn = self._main_window._conn  # noqa: SLF001
        task_repo = TaskRepository(conn)
        item_repo = TaskItemRepository(conn)

        # 创建 Task
        task = Task(
            id=None,
            source_type="batch",
            source_url=None,
            status="pending",
            total_items=len(aweme_ids),
            download_dir=download_dir,
        )
        task_id = task_repo.create(task)
        logger.info("已创建 Task id=%s, %d 项", task_id, len(aweme_ids))

        # 创建 TaskItems
        item_ids: list[int] = []
        for aweme_id in aweme_ids:
            item = TaskItem(
                id=None,
                task_id=task_id,
                aweme_id=aweme_id,
                url="",
                status="pending",
            )
            item_id = item_repo.create(item)
            item_ids.append(item_id)

        # 提交到下载队列
        control = self._download_bridge._control_signals  # noqa: SLF001
        control.start_download.emit(item_ids)

        # 刷新下载页
        page = self._pages.get("download")
        if page is not None:
            page.refresh()

        # 切换到下载页
        self._switch_page(0)
        logger.info("已提交 %d 项到下载队列", len(item_ids))

    # === CookiePage 信号槽 ===

    def _on_add_cookie(self, content: str, label: str) -> None:
        """添加 Cookie 到 DB。"""
        conn = self._main_window._conn  # noqa: SLF001
        repo = CookieRepository(conn)
        cookie = Cookie(id=None, content=content, label=label or None)
        repo.add(cookie)
        logger.info("已添加 Cookie: label=%s", label)

        # 刷新 Cookie 页
        page = self._pages.get("cookie")
        if page is not None:
            page.refresh()

    def _on_remove_cookie(self, cookie_id: int) -> None:
        """从 DB 删除 Cookie。"""
        conn = self._main_window._conn  # noqa: SLF001
        repo = CookieRepository(conn)
        repo.remove(cookie_id)
        logger.info("已删除 Cookie id=%s", cookie_id)

        # 刷新 Cookie 页
        page = self._pages.get("cookie")
        if page is not None:
            page.refresh()

    # === SettingsPage 信号槽 ===

    def _on_settings_changed(self, config: dict) -> None:
        """配置变更通知（配置已在页面中保存到 DB）。"""
        logger.debug("配置已变更: %s", config)

    def _on_export_logs(self) -> None:
        """打开日志目录。"""
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        log_dir = os.path.join(base, "DouyinCatcher", "logs")
        if os.path.isdir(log_dir):
            QDesktopServices.openUrl(log_dir)
        else:
            QMessageBox.information(
                self._main_window,
                "日志目录",
                f"日志目录尚未创建：\n{log_dir}\n\n应用运行后将自动生成日志文件。",
                QMessageBox.StandardButton.Ok,
            )

    # === 辅助方法 ===

    def _switch_page(self, index: int) -> None:
        """切换主窗口页面。

        Args:
            index: 目标页面索引（0=下载, 1=抓取, 2=Cookie, 3=设置）。
        """
        stacked = self._main_window._stacked_widget  # noqa: SLF001
        nav_bar = self._main_window._nav_bar  # noqa: SLF001
        if stacked is not None:
            stacked.setCurrentIndex(index)
        if nav_bar is not None:
            nav_bar.set_current_page(index)
