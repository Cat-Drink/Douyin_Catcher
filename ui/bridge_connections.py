"""Bridge 连接层模块。

将 MainWindow 与 ``DownloadBridge`` / ``CrawlerBridge`` 的信号连接到
UI 槽函数，建立 UI 与工作线程之间的信号/槽粘合层。

严格遵循设计文档第 2.3 节（线程模型）与 v0.0.7 计划文档任务 6。

v0.0.7 职责边界：
    - 只做信号连接，槽函数为占位实现（记录日志）
    - 具体 UI 更新逻辑（刷新任务行进度、更新状态栏计数等）在 v0.0.8 实现

信号连接表（以 v0.0.6 实际信号签名为准）::

    DownloadBridge.worker_signals:
        progress_updated(list)       → _on_progress_updated
        item_completed(int)          → _on_item_completed
        item_failed(int, str)        → _on_item_failed
        cookie_invalid(str)          → _on_cookie_invalid
        task_completed(int)          → _on_task_completed

    CrawlerBridge.worker_signals:
        parse_progress(int, int)     → _on_parse_progress
        parse_completed(list)        → _on_parse_completed
        parse_failed(str)            → _on_parse_failed
        cookie_test_result(int,bool,str) → _on_cookie_test_result
        home_fetch_progress(int,int) → _on_home_fetch_progress
        home_fetch_completed(list)   → _on_home_fetch_completed
        home_fetch_failed(str)       → _on_home_fetch_failed
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.logger import get_logger
from ui.main_window import MainWindow
from worker.crawler_bridge import CrawlerBridge
from worker.download_bridge import DownloadBridge

logger = get_logger(__name__)


class BridgeConnections:
    """Bridge 信号连接粘合层。

    连接 DownloadBridge / CrawlerBridge 的 WorkerSignals 到 UI 槽函数。
    v0.0.7 槽函数为占位实现（记录日志），v0.0.8 填充具体 UI 更新逻辑。

    线程安全：
        Bridge 信号通过 Qt 的 Signal 机制跨线程传递，槽函数在主线程执行，
        可安全操作 UI。不要在槽函数中直接调用 Bridge 的控制方法。
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
        """连接所有 Bridge 信号到对应槽函数。"""
        self._connect_download_bridge_signals()
        self._connect_crawler_bridge_signals()
        logger.info("Bridge 信号连接已建立")

    def _connect_download_bridge_signals(self) -> None:
        """连接 DownloadBridge 的 WorkerSignals 到槽函数。"""
        signals = self._download_bridge._worker_signals  # noqa: SLF001
        signals.progress_updated.connect(self._on_progress_updated)
        signals.item_completed.connect(self._on_item_completed)
        signals.item_failed.connect(self._on_item_failed)
        signals.cookie_invalid.connect(self._on_cookie_invalid)
        signals.task_completed.connect(self._on_task_completed)
        logger.debug("DownloadBridge 信号已连接")

    def _connect_crawler_bridge_signals(self) -> None:
        """连接 CrawlerBridge 的 WorkerSignals 到槽函数。"""
        signals = self._crawler_bridge._worker_signals  # noqa: SLF001
        signals.parse_progress.connect(self._on_parse_progress)
        signals.parse_completed.connect(self._on_parse_completed)
        signals.parse_failed.connect(self._on_parse_failed)
        signals.cookie_test_result.connect(self._on_cookie_test_result)
        signals.home_fetch_progress.connect(self._on_home_fetch_progress)
        signals.home_fetch_completed.connect(self._on_home_fetch_completed)
        signals.home_fetch_failed.connect(self._on_home_fetch_failed)
        logger.debug("CrawlerBridge 信号已连接")

    # === DownloadBridge 槽函数（占位） ===

    def _on_progress_updated(self, updates: list) -> None:
        """下载进度更新（批量，500ms 节流）。

        v0.0.8 实现：更新任务行进度条、百分比。
        """
        logger.debug("进度更新：%d 项", len(updates))

    def _on_item_completed(self, task_item_id: int) -> None:
        """单个任务项下载完成。

        v0.0.8 实现：更新任务行状态为完成、刷新状态栏计数。
        """
        logger.info("任务项完成：id=%s", task_item_id)

    def _on_item_failed(self, task_item_id: int, fail_reason: str) -> None:
        """单个任务项下载失败。

        v0.0.8 实现：更新任务行状态为失败、显示失败原因、刷新状态栏计数。
        """
        logger.warning("任务项失败：id=%s 原因=%s", task_item_id, fail_reason)

    def _on_cookie_invalid(self, message: str) -> None:
        """Cookie 失效通知。

        v0.0.8 实现：弹窗提示 Cookie 失效、引导跳转 Cookie 配置页。
        """
        logger.warning("Cookie 失效：%s", message)

    def _on_task_completed(self, task_id: int) -> None:
        """某任务下所有子项完成。

        v0.0.8 实现：更新任务状态、刷新状态栏计数。
        """
        logger.info("任务全部完成：task_id=%s", task_id)

    # === CrawlerBridge 槽函数（占位） ===

    def _on_parse_progress(self, current: int, total: int) -> None:
        """链接解析进度。

        v0.0.8 实现：更新 FetchPage 解析进度条。
        """
        logger.debug("解析进度：%d/%d", current, total)

    def _on_parse_completed(self, results: list) -> None:
        """链接解析完成。

        v0.0.8 实现：传递给 FetchPage 渲染解析结果列表。
        """
        logger.info("解析完成：%d 条", len(results))

    def _on_parse_failed(self, reason: str) -> None:
        """链接解析失败。

        v0.0.8 实现：在 FetchPage 显示错误提示。
        """
        logger.warning("解析失败：%s", reason)

    def _on_cookie_test_result(self, cookie_id: int, is_valid: bool, message: str) -> None:
        """Cookie 测试结果。

        v0.0.8 实现：传递给 CookiePage 更新状态灯与状态文字。
        """
        logger.info("Cookie 测试结果：id=%s valid=%s msg=%s", cookie_id, is_valid, message)

    def _on_home_fetch_progress(self, current: int, total: int) -> None:
        """主页抓取进度。

        v0.0.8 实现：更新 FetchPage 抓取进度。
        """
        logger.debug("主页抓取进度：%d/%d", current, total)

    def _on_home_fetch_completed(self, results: list) -> None:
        """主页抓取完成。

        v0.0.8 实现：传递给 FetchPage 渲染主页抓取结果。
        """
        logger.info("主页抓取完成：%d 条", len(results))

    def _on_home_fetch_failed(self, reason: str) -> None:
        """主页抓取失败。

        v0.0.8 实现：在 FetchPage 显示错误提示。
        """
        logger.warning("主页抓取失败：%s", reason)
