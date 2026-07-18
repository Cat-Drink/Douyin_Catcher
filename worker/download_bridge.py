"""下载引擎桥接器模块。

连接 UI 控制信号 → ``Scheduler`` 方法，
连接 ``Scheduler`` 回调与 ``ProgressReporter`` 回调 → UI 更新信号；
并负责应用启动时的断点续传恢复。

严格遵循设计文档 5 节（下载引擎信号发射器）与 v0.0.6 计划文档任务 3。

职责边界：
    - 桥接器只做转发，不含下载业务逻辑
    - 业务逻辑在 ``downloader/`` 的 ``Scheduler`` / ``Downloader``
    - 信号 ↔ 方法的映射与数据结构转换在本模块完成

Scheduler 回调设置机制：
    Scheduler 在 ``__init__`` 中接收回调参数（``on_item_completed`` 等），
    本桥接器在 ``_connect_scheduler_callbacks`` 中直接设置 Scheduler 的
    私有属性 ``_on_item_completed`` / ``_on_item_failed`` 以及
    ``_progress_reporter._on_progress``，将回调转发为 UI 信号。
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from app.logger import get_logger
from app.models import TaskItem
from app.repositories import CookieRepository, TaskItemRepository, TaskRepository
from crawlers.exceptions import CookieInvalidError
from crawlers.video_parser import VideoParser
from downloader.scheduler import Scheduler
from worker.async_worker import AsyncWorker
from worker.signals import ControlSignals, WorkerSignals

logger = get_logger(__name__)


class DownloadBridge(QObject):
    """下载引擎桥接器：UI 控制信号 ↔ Scheduler 方法 + 回调 → UI 信号。

    信号流向：
        UI → ``ControlSignals.start_download`` → ``on_start_download`` 槽 →
        ``async_worker.submit`` → ``_do_start_download`` → ``scheduler.add_task_items``

        ``scheduler`` 回调 → ``on_item_completed`` / ``on_item_failed`` / ``on_progress`` →
        ``worker_signals`` emit → UI 槽

    依赖注入：
        所有依赖通过构造函数注入，由后续 v0.0.7 的 ``main.py`` 装配。
    """

    def __init__(
        self,
        async_worker: AsyncWorker,
        scheduler: Scheduler,
        task_item_repository: TaskItemRepository,
        task_repository: TaskRepository,
        worker_signals: WorkerSignals,
        control_signals: ControlSignals,
        video_parser: VideoParser,
        cookie_repository: CookieRepository,
        parent=None,
    ) -> None:
        """初始化下载桥接器。

        Args:
            async_worker: 异步工作线程，提供 submit 调度协程
            scheduler: 下载调度器
            task_item_repository: 任务项仓库
            task_repository: 任务仓库
            worker_signals: 工作线程->UI 信号
            control_signals: UI->工作线程控制信号
            video_parser: 视频解析器，用于下载前解析无水印直链
            cookie_repository: Cookie 仓库，用于解析直链时取 Cookie
            parent: Qt 父对象
        """
        super().__init__(parent)
        self._async_worker = async_worker
        self._scheduler = scheduler
        self._task_item_repo = task_item_repository
        self._task_repo = task_repository
        self._worker_signals = worker_signals
        self._control_signals = control_signals
        self._video_parser = video_parser
        self._cookie_repo = cookie_repository

        self._connect_signals()
        self._connect_scheduler_callbacks()

    def init_scheduler(self, concurrency: int) -> None:
        """初始化 Scheduler：设置并发数，启动调度循环。

        Args:
            concurrency: 并发下载数
        """
        self._scheduler.set_max_concurrent(concurrency)
        self._async_worker.submit(self._scheduler.start())
        logger.info("Scheduler 已初始化，并发数=%d", concurrency)

    # === UI 控制信号槽 ===

    def on_start_download(self, task_item_ids: list) -> None:
        """接收 ``control_signals.start_download``：提交协程到工作线程。

        Args:
            task_item_ids: 待下载的任务项 ID 列表
        """
        self._async_worker.submit(self._do_start_download(task_item_ids))

    def on_pause_download(self, task_item_id: int) -> None:
        """接收 ``control_signals.pause_download``。

        Args:
            task_item_id: 任务项 ID
        """
        self._async_worker.submit(self._scheduler.pause(task_item_id))

    def on_resume_download(self, task_item_id: int) -> None:
        """接收 ``control_signals.resume_download``。

        Args:
            task_item_id: 任务项 ID
        """
        self._async_worker.submit(self._scheduler.resume(task_item_id))

    def on_pause_all(self) -> None:
        """接收 ``control_signals.pause_all``。"""
        self._async_worker.submit(self._scheduler.pause_all())

    def on_resume_all(self) -> None:
        """接收 ``control_signals.resume_all``。"""
        self._async_worker.submit(self._scheduler.resume_all())

    # === Scheduler / ProgressReporter 回调 ===

    def on_item_completed(self, task_item_id: int) -> None:
        """Scheduler 的 ``on_item_completed`` 回调。

        发射 ``worker_signals.item_completed`` 信号，
        并检查所属 task 是否全部完成。

        Args:
            task_item_id: 已完成的任务项 ID
        """
        self._worker_signals.item_completed.emit(task_item_id)
        self._check_task_completed(task_item_id)

    def on_item_failed(self, task_item_id: int, reason: str) -> None:
        """Scheduler 的 ``on_item_failed`` 回调。

        Args:
            task_item_id: 失败的任务项 ID
            reason: 失败原因
        """
        self._worker_signals.item_failed.emit(task_item_id, reason)

    def on_progress(self, updates: list) -> None:
        """``ProgressReporter`` 的 ``on_progress`` 回调。

        Args:
            updates: ``list[ProgressUpdate]``，批量进度更新
        """
        self._worker_signals.progress_updated.emit(updates)

    def on_all_cookies_invalid(self) -> None:
        """Cookie 池全部失效回调。

        发射 ``worker_signals.cookie_invalid`` 信号。
        """
        self._worker_signals.cookie_invalid.emit("所有 Cookie 已失效，请更新")

    # === 断点续传恢复 ===

    def restore_pending_tasks(self) -> None:
        """应用启动时调用：恢复 pending/paused 任务。

        通过 ``async_worker.submit`` 在工作线程执行
        ``_do_restore_pending_tasks``，对 url 为空的 pending 项先解析直链。
        """
        self._async_worker.submit(self._do_restore_pending_tasks())
        logger.info("已提交断点续传恢复任务")

    async def _do_restore_pending_tasks(self) -> None:
        """工作线程执行：恢复 pending/paused 任务。

        对 url 为空的项调用 VideoParser 解析直链后再入队。
        """
        # downloading -> paused（上次中断了）
        reset_count = self._task_item_repo.reset_downloading_to_paused()
        if reset_count > 0:
            logger.info("启动恢复：将 %d 个 downloading 重置为 paused", reset_count)

        pending = self._task_item_repo.get_by_status("pending")
        paused = self._task_item_repo.get_by_status("paused")

        # 所有 url 为空的项（无论 pending 还是 paused）都需先解析直链
        all_items = pending + paused
        resolved_items: list[TaskItem] = []
        for item in all_items:
            if not item.url and item.aweme_id:
                resolved = await self._resolve_download_url(item)
                if resolved is not None:
                    resolved_items.append(resolved)
            else:
                resolved_items.append(item)

        if resolved_items:
            self._scheduler.add_task_items(resolved_items)
            logger.info(
                "启动恢复：加入队列 %d 项（pending=%d, paused=%d）",
                len(resolved_items),
                len(pending),
                len(paused),
            )

    # === 内部协程 ===

    async def _do_start_download(self, task_item_ids: list) -> None:
        """工作线程执行：从 DB 取 TaskItem，解析下载直链，加入下载队列。

        对于 url 为空的 TaskItem，调用 VideoParser.parse_video 解析无水印直链
        与类型，回填到 DB 后再加入队列。

        v0.1.6：成功加入队列后 emit ``download_started(task_id)`` 信号，
        供 FetchPage 清理输入框/结果列表/过滤栏（用户反馈 #6）。task_id 从
        首个成功入队的 TaskItem 反查；若全部项解析失败不 emit，保留抓取页内容
        供用户重试。

        Args:
            task_item_ids: 任务项 ID 列表
        """
        items = []
        for item_id in task_item_ids:
            item = self._task_item_repo.get(item_id)
            if item is None:
                logger.warning("task_item id=%s 不存在，跳过", item_id)
                continue
            # url 为空时通过 VideoParser 解析直链
            if not item.url and item.aweme_id:
                resolved = await self._resolve_download_url(item)
                if resolved is None:
                    continue
                item = resolved
            items.append(item)
        if items:
            self._scheduler.add_task_items(items)
            logger.info("已加入下载队列 %d 项", len(items))
            # v0.1.6：通知 UI 入队成功，触发 FetchPage 清理
            task_id = items[0].task_id
            self._worker_signals.download_started.emit(task_id)

    async def _resolve_download_url(self, item: TaskItem) -> TaskItem | None:
        """解析 TaskItem 的下载直链与类型。

        从 Cookie 仓库取 valid Cookie，调用 VideoParser.parse_video 获取
        no_watermark_url（视频）或 image_urls（图集），回填 DB。

        Args:
            item: 待解析的 TaskItem（url 为空）

        Returns:
            更新后的 TaskItem；解析失败返回 None
        """
        aweme_id = item.aweme_id
        if aweme_id is None:
            logger.warning("task_item id=%s aweme_id 为空，无法解析直链", item.id)
            self._task_item_repo.update_status(item.id, "failed", fail_reason="aweme_id 为空")
            self._worker_signals.item_failed.emit(item.id, "aweme_id 为空")
            return None

        cookie = self._cookie_repo.get_valid()
        if cookie is None:
            logger.warning("无可用 Cookie，无法解析直链 aweme_id=%s", aweme_id)
            self._task_item_repo.update_status(item.id, "failed", fail_reason="无可用 Cookie")
            self._worker_signals.item_failed.emit(item.id, "无可用 Cookie")
            return None

        try:
            video_info = await self._video_parser.parse_video(aweme_id, cookie.content)
        except CookieInvalidError:
            logger.warning("解析直链时 Cookie 失效 aweme_id=%s", aweme_id)
            self._task_item_repo.update_status(item.id, "failed", fail_reason="Cookie 失效")
            self._worker_signals.item_failed.emit(item.id, "Cookie 失效")
            return None
        except Exception as e:
            logger.exception("解析直链失败 aweme_id=%s", aweme_id)
            self._task_item_repo.update_status(item.id, "failed", fail_reason=str(e))
            self._worker_signals.item_failed.emit(item.id, str(e))
            return None

        # 构造下载 URL：图集为换行分隔的图片 URL，视频为无水印直链
        if video_info.type == "image_set" and video_info.image_urls:
            download_url = "\n".join(video_info.image_urls)
        else:
            download_url = video_info.no_watermark_url or ""

        if not download_url:
            logger.warning("解析到的下载直链为空 aweme_id=%s", aweme_id)
            self._task_item_repo.update_status(item.id, "failed", fail_reason="下载直链为空")
            self._worker_signals.item_failed.emit(item.id, "下载直链为空")
            return None

        # 回填 DB
        self._task_item_repo.update_url_and_type(
            item.id,
            download_url,
            video_info.type,
            title=video_info.title or None,
            author=video_info.author or None,
            duration=video_info.duration,
            cover_url=video_info.cover_url or None,
        )
        logger.info(
            "已解析直链 task_item id=%s type=%s aweme_id=%s",
            item.id,
            video_info.type,
            aweme_id,
        )

        # 返回更新后的 TaskItem（重新从 DB 读取以获取完整字段）
        return self._task_item_repo.get(item.id)

    def _check_task_completed(self, task_item_id: int) -> None:
        """检查所属 task 是否全部完成。

        Args:
            task_item_id: 刚完成的任务项 ID
        """
        item = self._task_item_repo.get(task_item_id)
        if item is None:
            return
        task_id = item.task_id
        all_items = self._task_item_repo.get_by_task(task_id)
        if not all_items:
            return
        if all(i.status == "completed" for i in all_items):
            self._worker_signals.task_completed.emit(task_id)
            logger.info("task id=%s 全部子项完成", task_id)

    # === 信号连接 ===

    def _connect_signals(self) -> None:
        """连接 UI → 工作线程控制信号到对应槽。"""
        self._control_signals.start_download.connect(self.on_start_download)
        self._control_signals.pause_download.connect(self.on_pause_download)
        self._control_signals.resume_download.connect(self.on_resume_download)
        self._control_signals.pause_all.connect(self.on_pause_all)
        self._control_signals.resume_all.connect(self.on_resume_all)
        logger.debug("DownloadBridge 控制信号已连接")

    def _connect_scheduler_callbacks(self) -> None:
        """设置 Scheduler 回调：将 Scheduler/ProgressReporter 回调桥接到 UI 信号。

        Scheduler 的回调在 ``__init__`` 中以参数形式接收，存储为私有属性。
        此处直接设置私有属性，将回调转发为 UI 信号。
        """
        self._scheduler._on_item_completed = self.on_item_completed
        self._scheduler._on_item_failed = self.on_item_failed
        self._scheduler._progress_reporter._on_progress = self.on_progress
        logger.debug("Scheduler 回调已桥接到 DownloadBridge")
