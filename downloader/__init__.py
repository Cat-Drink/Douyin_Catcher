"""下载引擎核心模块。

导出进度节流器、单项下载器、任务调度器三大组件及其数据类与常量。
"""

from downloader.constants import (
    LARGE_FILE_THRESHOLD,
    LONG_VIDEO_DURATION_THRESHOLD,
    MAX_SEGMENTS,
    SEGMENT_SIZE,
)
from downloader.downloader import (
    CHUNK_SIZE,
    MAX_RETRY_COUNT,
    PERSIST_INTERVAL_BYTES,
    PERSIST_INTERVAL_SECONDS,
    RATE_LIMITED_STATUS_CODES,
    RETRY_BACKOFF_BASE,
    Downloader,
    DownloadResult,
)
from downloader.progress_reporter import (
    DEFAULT_FLUSH_INTERVAL_MS,
    ProgressReporter,
    ProgressUpdate,
)
from downloader.scheduler import (
    DEFAULT_DOWNLOAD_CONNECT_TIMEOUT,
    DEFAULT_DOWNLOAD_READ_TIMEOUT,
    DEFAULT_MAX_CONCURRENT,
    DOWNLOAD_DEFAULT_HEADERS,
    MAX_CONCURRENT_LIMIT,
    Scheduler,
)

__all__ = [
    # progress_reporter
    "ProgressReporter",
    "ProgressUpdate",
    "DEFAULT_FLUSH_INTERVAL_MS",
    # downloader
    "Downloader",
    "DownloadResult",
    "CHUNK_SIZE",
    "PERSIST_INTERVAL_SECONDS",
    "PERSIST_INTERVAL_BYTES",
    "MAX_RETRY_COUNT",
    "RETRY_BACKOFF_BASE",
    "RATE_LIMITED_STATUS_CODES",
    # constants（v0.1.3：集中定义）
    "SEGMENT_SIZE",
    "MAX_SEGMENTS",
    "LARGE_FILE_THRESHOLD",
    "LONG_VIDEO_DURATION_THRESHOLD",
    # scheduler
    "Scheduler",
    "DEFAULT_MAX_CONCURRENT",
    "MAX_CONCURRENT_LIMIT",
    "DEFAULT_DOWNLOAD_CONNECT_TIMEOUT",
    "DEFAULT_DOWNLOAD_READ_TIMEOUT",
    "DOWNLOAD_DEFAULT_HEADERS",
]
