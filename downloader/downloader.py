"""单项下载器模块。

实现单个 ``TaskItem`` 的下载逻辑，包括 httpx Range 请求、流式写入、
失败重试、图集并发、取消处理。严格遵循设计文档 5.2 节（下载流程）
与 5.3 节（重试策略）。

下载流程（设计文档 5.2 节）：
1. 从 SQLite 取 task_item，置为 downloading
2. 检查 .part 文件 → 读取已下载字节数（断点续传）
3. httpx Range 请求
4. 流式接收 64KB 块 → 追加写入 .part → 每 5s/1MB 持久化 → 更新进度
5. 完成 → .part 重命名为最终文件 → status=completed

重试策略（设计文档 5.3 节）：
- 网络异常 / 5xx / 461 / 412 → 重试，2^retry_count 秒指数退避
- 3 次上限 → status=failed
- 4xx（非限流）→ 直接失败不重试
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass

import httpx

from app.logger import get_logger
from app.repositories import TaskItemRepository, TaskRepository
from downloader.progress_reporter import ProgressReporter

logger = get_logger(__name__)

# === 常量（设计文档 5.2 / 5.3 节）===

# 流式接收块大小 64KB
CHUNK_SIZE: int = 64 * 1024

# 进度持久化间隔 5 秒
PERSIST_INTERVAL_SECONDS: int = 5

# 进度持久化间隔 1MB
PERSIST_INTERVAL_BYTES: int = 1024 * 1024

# 最大重试次数 3
MAX_RETRY_COUNT: int = 3

# 指数退避底数，等待 2^retry_count 秒
RETRY_BACKOFF_BASE: int = 2

# 风控限流状态码（与爬虫层一致，触发重试）
RATE_LIMITED_STATUS_CODES: frozenset[int] = frozenset({461, 412})


@dataclass(frozen=True)
class DownloadResult:
    """单项下载结果。

    Attributes:
        success: 是否下载成功
        local_path: 成功时的本地文件路径，失败为 None
        error: 失败原因，成功为 None
    """

    success: bool
    local_path: str | None = None
    error: str | None = None


class Downloader:
    """单项下载器。

    通过 httpx Range 请求流式下载文件，支持断点续传、失败重试、图集并发。
    进度通过 ProgressReporter 节流上报，状态持久化到 SQLite。

    注意：Downloader **不**修改 status 为 paused（归 Scheduler），
    仅在下载完成时置 completed、失败时置 failed。
    """

    def __init__(
        self,
        progress_reporter: ProgressReporter,
        http_client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        conn: sqlite3.Connection,
    ) -> None:
        """初始化下载器。

        Args:
            progress_reporter: 进度节流器
            http_client: httpx 异步客户端
            semaphore: 并发信号量（图集子任务也受此约束）
            conn: SQLite 连接（用于状态持久化与 download_dir 查询）
        """
        self._progress_reporter = progress_reporter
        self._http_client = http_client
        self._semaphore = semaphore
        self._conn = conn
        self._item_repo = TaskItemRepository(conn)
        self._task_repo = TaskRepository(conn)
