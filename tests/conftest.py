"""pytest fixtures。

提供内存数据库、各 Repository、样本数据等 fixtures，供测试使用。
每个测试函数独立内存数据库，互不影响。
"""

from __future__ import annotations

import sqlite3

import pytest

from app import database
from app.models import Task, TaskItem
from app.repositories import (
    ConfigRepository,
    CookieRepository,
    MetadataRepository,
    TaskItemRepository,
    TaskRepository,
)


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """返回内存数据库连接（已初始化），测试结束后关闭。

    每个测试函数独立内存数据库，互不影响。
    """
    conn = database.get_memory_connection()
    yield conn
    conn.close()


@pytest.fixture
def task_repo(memory_db: sqlite3.Connection) -> TaskRepository:
    """返回 TaskRepository 实例。"""
    return TaskRepository(memory_db)


@pytest.fixture
def item_repo(memory_db: sqlite3.Connection) -> TaskItemRepository:
    """返回 TaskItemRepository 实例。"""
    return TaskItemRepository(memory_db)


@pytest.fixture
def cookie_repo(memory_db: sqlite3.Connection) -> CookieRepository:
    """返回 CookieRepository 实例。"""
    return CookieRepository(memory_db)


@pytest.fixture
def config_repo(memory_db: sqlite3.Connection) -> ConfigRepository:
    """返回 ConfigRepository 实例。"""
    return ConfigRepository(memory_db)


@pytest.fixture
def metadata_repo(memory_db: sqlite3.Connection) -> MetadataRepository:
    """返回 MetadataRepository 实例。"""
    return MetadataRepository(memory_db)


@pytest.fixture
def sample_task() -> Task:
    """返回一个可插入的 Task 实例（id=None，时间戳由 Repository 填充）。"""
    return Task(
        id=None,
        source_type="single",
        source_url="https://www.douyin.com/video/123456",
        status="pending",
        total_items=1,
        completed_items=0,
        download_dir="C:/Downloads/DouyinCatcher",
    )


@pytest.fixture
def sample_task_item(sample_task: Task, task_repo: TaskRepository) -> TaskItem:
    """先插入 sample_task 拿到 task_id，构造并返回 TaskItem（未插入，供测试按需插入）。"""
    task_id = task_repo.create(sample_task)
    return TaskItem(
        id=None,
        task_id=task_id,
        aweme_id="aweme_001",
        url="https://example.com/video.mp4",
        title="测试视频",
        author="测试作者",
        author_sec_id="sec_uid_001",
        type="video",
        duration="15s",
        image_count=None,
        cover_url="https://example.com/cover.jpg",
        status="pending",
        downloaded_bytes=0,
        total_bytes=1024000,
        retry_count=0,
        fail_reason=None,
        local_path=None,
    )
