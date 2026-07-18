"""v0.1.7 图文类型下载流程单元测试。

覆盖预览流程的关键改动：
    - PreviewItem dataclass（from_video_info / to_result_dict）
    - _filter_image_urls / _build_download_url 辅助函数
    - CrawlerBridge.parse_for_preview 预览解析流程
    - DB schema v1→v2 迁移（task_items.selected_image_indices）
    - TaskItemRepository.update_selected_image_indices
    - TaskItemWidget 图集类型"M/N 张"进度显示
    - PreviewItemWidget 图集展开与图片级勾选联动

不依赖真实网络与真实 Bridge；CrawlerBridge 测试使用 mock URLParser/VideoParser。
"""

from __future__ import annotations

import json
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock

from app.database import SCHEMA_VERSION, _column_exists, migrate
from app.models import Task, TaskItem
from app.preview_models import PreviewItem
from app.repositories import TaskItemRepository, TaskRepository
from crawlers.exceptions import CookieInvalidError, InvalidURLFormatError
from crawlers.url_parser import ParsedURL
from crawlers.video_parser import VideoInfo
from ui.pages.fetch_page import PreviewItemWidget
from ui.widgets.task_item_widget import TaskItemWidget
from worker.crawler_bridge import CrawlerBridge
from worker.download_bridge import _filter_image_urls
from worker.signals import ControlSignals, WorkerSignals

# ==================== PreviewItem 测试 ====================


def _make_video_info(
    aweme_id: str = "aweme_001",
    type_: str = "video",
    image_urls: list[str] | None = None,
    no_watermark_url: str | None = "https://example.com/v.mp4",
    duration: str | None = "00:15",
) -> VideoInfo:
    """构造 VideoInfo 实例。"""
    return VideoInfo(
        aweme_id=aweme_id,
        type=type_,  # type: ignore[arg-type]
        title="测试作品",
        author="测试作者",
        author_sec_id="sec_uid_001",
        duration=duration,
        cover_url="https://example.com/cover.jpg",
        no_watermark_url=no_watermark_url,
        image_urls=image_urls or [],
        publish_time="2026-07-11T10:00:00Z",
        like_count=100,
        comment_count=10,
        share_count=5,
        collect_count=2,
        tags=["测试"],
        raw_json={"id": aweme_id},
    )


class TestPreviewItemFromVideoInfo:
    """PreviewItem.from_video_info 测试。"""

    def test_video_type_conversion(self) -> None:
        """视频类型 VideoInfo → PreviewItem 字段正确。"""
        info = _make_video_info(type_="video", no_watermark_url="https://v.mp4")
        item = PreviewItem.from_video_info(info)
        assert item.aweme_id == "aweme_001"
        assert item.type == "video"
        assert item.title == "测试作品"
        assert item.cover_url == "https://example.com/cover.jpg"
        assert item.video_url == "https://v.mp4"
        assert item.image_urls == []
        assert item.image_count is None
        assert item.duration == "00:15"
        assert item.author == "测试作者"
        assert item.author_sec_id == "sec_uid_001"

    def test_image_set_type_conversion(self) -> None:
        """图集类型 VideoInfo → PreviewItem，image_count 自动计算。"""
        urls = ["https://img1.jpg", "https://img2.jpg", "https://img3.jpg"]
        info = _make_video_info(
            type_="image_set",
            image_urls=urls,
            no_watermark_url=None,
            duration=None,
        )
        item = PreviewItem.from_video_info(info)
        assert item.type == "image_set"
        assert item.image_urls == urls
        assert item.image_count == 3
        assert item.video_url == ""
        assert item.duration is None

    def test_empty_fields_fallback(self) -> None:
        """VideoInfo 部分字段为 None 时 PreviewItem 使用空字符串兜底。"""
        info = VideoInfo(
            aweme_id="aweme_x",
            type="video",
            title="",
            author="",
            author_sec_id="",
            duration=None,
            cover_url="",
            no_watermark_url=None,
            image_urls=[],
            publish_time=None,
            like_count=0,
            comment_count=0,
            share_count=0,
            collect_count=0,
            tags=[],
            raw_json={},
        )
        item = PreviewItem.from_video_info(info)
        assert item.title == ""
        assert item.author == ""
        assert item.cover_url == ""
        assert item.video_url == ""
        assert item.image_urls == []
        assert item.image_count is None

    def test_image_urls_copied_not_shared(self) -> None:
        """from_video_info 应复制 image_urls 列表，避免与源对象共享引用。"""
        urls = ["https://a.jpg", "https://b.jpg"]
        info = _make_video_info(
            type_="image_set", image_urls=urls, no_watermark_url=None, duration=None
        )
        item = PreviewItem.from_video_info(info)
        item.image_urls.append("https://c.jpg")
        assert len(info.image_urls) == 2
        assert len(item.image_urls) == 3


class TestPreviewItemToResultDict:
    """PreviewItem.to_result_dict 测试。"""

    def test_to_result_dict_fields(self) -> None:
        """to_result_dict 返回包含所有字段。"""
        item = PreviewItem(
            aweme_id="aweme_001",
            title="标题",
            cover_url="https://cover.jpg",
            type="image_set",
            duration=None,
            image_urls=["https://1.jpg", "https://2.jpg"],
            video_url="",
            author="作者",
            author_sec_id="sec_uid",
            image_count=2,
        )
        data = item.to_result_dict()
        assert data["aweme_id"] == "aweme_001"
        assert data["title"] == "标题"
        assert data["cover_url"] == "https://cover.jpg"
        assert data["type"] == "image_set"
        assert data["duration"] is None
        assert data["image_urls"] == ["https://1.jpg", "https://2.jpg"]
        assert data["video_url"] == ""
        assert data["author"] == "作者"
        assert data["author_sec_id"] == "sec_uid"
        assert data["image_count"] == 2

    def test_to_result_dict_image_urls_is_copy(self) -> None:
        """to_result_dict 返回的 image_urls 应是副本，修改不影响原对象。"""
        item = PreviewItem(
            aweme_id="x",
            title="",
            cover_url="",
            type="image_set",
            image_urls=["https://a.jpg"],
        )
        data = item.to_result_dict()
        data["image_urls"].append("https://b.jpg")
        assert len(item.image_urls) == 1


# ==================== _filter_image_urls 测试 ====================


class TestFilterImageUrls:
    """_filter_image_urls 辅助函数测试（download_bridge.py）。"""

    def test_empty_indices_returns_all(self) -> None:
        """空字符串表示全选，返回全部 URL。"""
        urls = ["https://a.jpg", "https://b.jpg", "https://c.jpg"]
        result = _filter_image_urls(urls, "")
        assert result == urls

    def test_partial_indices_filters(self) -> None:
        """部分索引 JSON 数组，仅返回指定索引的 URL。"""
        urls = ["https://a.jpg", "https://b.jpg", "https://c.jpg"]
        result = _filter_image_urls(urls, "[0,2]")
        assert result == ["https://a.jpg", "https://c.jpg"]

    def test_all_indices_in_json_returns_all(self) -> None:
        """JSON 包含全部索引时返回全部 URL。"""
        urls = ["https://a.jpg", "https://b.jpg"]
        result = _filter_image_urls(urls, "[0,1]")
        assert result == urls

    def test_invalid_json_returns_all(self) -> None:
        """非法 JSON 按全选处理。"""
        urls = ["https://a.jpg", "https://b.jpg"]
        result = _filter_image_urls(urls, "not a json")
        assert result == urls

    def test_non_list_json_returns_all(self) -> None:
        """JSON 解析为非 list（如 dict/str）时按全选处理。"""
        urls = ["https://a.jpg", "https://b.jpg"]
        result = _filter_image_urls(urls, '{"key": 1}')
        assert result == urls

    def test_out_of_range_indices_ignored(self) -> None:
        """越界索引被忽略，不抛异常。"""
        urls = ["https://a.jpg", "https://b.jpg"]
        result = _filter_image_urls(urls, "[0,5,-1,10]")
        assert result == ["https://a.jpg"]

    def test_non_int_indices_ignored(self) -> None:
        """非整数索引被忽略。"""
        urls = ["https://a.jpg", "https://b.jpg"]
        result = _filter_image_urls(urls, '[0, "1", 1]')
        assert result == ["https://a.jpg", "https://b.jpg"]

    def test_empty_urls_returns_empty(self) -> None:
        """空 URL 列表，无论 indices 如何都返回空。"""
        assert _filter_image_urls([], "") == []
        assert _filter_image_urls([], "[0,1]") == []


# ==================== _build_download_url 测试 ====================


class TestBuildDownloadUrl:
    """_build_download_url 辅助函数测试（bridge_connections.py）。"""

    def test_image_set_all_selected(self) -> None:
        """图集类型 + 空字符串（全选）→ 拼接所有 image_urls。"""
        from ui.bridge_connections import _build_download_url

        data = {"image_urls": ["https://a.jpg", "https://b.jpg"]}
        url = _build_download_url(data, "image_set", "")
        assert url == "https://a.jpg\nhttps://b.jpg"

    def test_image_set_partial_selected(self) -> None:
        """图集类型 + 部分选择 → 拼接指定索引的 URL。"""
        from ui.bridge_connections import _build_download_url

        data = {"image_urls": ["https://a.jpg", "https://b.jpg", "https://c.jpg"]}
        url = _build_download_url(data, "image_set", "[0,2]")
        assert url == "https://a.jpg\nhttps://c.jpg"

    def test_image_set_empty_urls(self) -> None:
        """图集类型但无 image_urls → 返回空字符串（待下载阶段解析）。"""
        from ui.bridge_connections import _build_download_url

        url = _build_download_url({}, "image_set", "")
        assert url == ""

    def test_video_type_returns_video_url(self) -> None:
        """视频类型返回 video_url。"""
        from ui.bridge_connections import _build_download_url

        data = {"video_url": "https://v.mp4"}
        url = _build_download_url(data, "video", "")
        assert url == "https://v.mp4"

    def test_video_type_missing_video_url(self) -> None:
        """视频类型无 video_url → 返回空字符串。"""
        from ui.bridge_connections import _build_download_url

        url = _build_download_url({}, "video", "")
        assert url == ""

    def test_image_set_invalid_json_falls_back_to_all(self) -> None:
        """图集类型 + 非法 JSON → 按全选拼接。"""
        from ui.bridge_connections import _build_download_url

        data = {"image_urls": ["https://a.jpg", "https://b.jpg"]}
        url = _build_download_url(data, "image_set", "invalid")
        assert url == "https://a.jpg\nhttps://b.jpg"


# ==================== CrawlerBridge.parse_for_preview 测试 ====================


def _make_parsed_url(
    url: str = "https://v.douyin.com/abc/",
    aweme_id: str = "aweme_001",
) -> ParsedURL:
    """构造 ParsedURL 实例。"""
    return ParsedURL(
        type="video",
        url=url,
        aweme_id=aweme_id,
        sec_user_id=None,
        original_text=url,
    )


def _make_cookie() -> MagicMock:
    """构造 mock Cookie。"""
    cookie = MagicMock()
    cookie.id = 1
    cookie.content = "ttwid=fake; msToken=fake"
    return cookie


def _make_mock_url_parser(return_aweme_id: str = "aweme_001") -> MagicMock:
    """构造 mock URLParser。"""
    parser = MagicMock()
    parser.parse = AsyncMock(return_value=_make_parsed_url(aweme_id=return_aweme_id))
    return parser


def _make_mock_video_parser(info: VideoInfo | None = None) -> MagicMock:
    """构造 mock VideoParser。"""
    parser = MagicMock()
    parser.parse_video = AsyncMock(return_value=info or _make_video_info())
    return parser


def _make_mock_cookie_repo(cookie: MagicMock | None = None) -> MagicMock:
    """构造 mock CookieRepository。"""
    repo = MagicMock()
    repo.get_valid = MagicMock(return_value=cookie or _make_cookie())
    return repo


def _make_bridge_with_preview(
    qapp,
    async_worker,
    url_parser: MagicMock | None = None,
    video_parser: MagicMock | None = None,
    cookie_repo: MagicMock | None = None,
) -> CrawlerBridge:
    """构造支持预览解析的 CrawlerBridge。"""
    bridge = CrawlerBridge(
        async_worker=async_worker,
        url_parser=url_parser or _make_mock_url_parser(),
        user_home_crawler=MagicMock(),
        cookie_tester=MagicMock(),
        cookie_repository=cookie_repo or _make_mock_cookie_repo(),
        worker_signals=WorkerSignals(),
        control_signals=ControlSignals(),
        video_parser=video_parser or _make_mock_video_parser(),
    )
    return bridge


class TestParseForPreview:
    """CrawlerBridge.parse_for_preview 流程测试。"""

    def test_preview_completed_emitted_on_success(self, qapp, async_worker) -> None:
        """成功解析 → emit preview_completed(list[PreviewItem])。"""
        info = _make_video_info(aweme_id="aweme_001", type_="video")
        video_parser = _make_mock_video_parser(info=info)
        bridge = _make_bridge_with_preview(qapp, async_worker, video_parser=video_parser)

        received: list[list[PreviewItem]] = []
        bridge._worker_signals.preview_completed.connect(lambda items: received.append(items))

        bridge.on_start_parse_for_preview("https://v.douyin.com/abc/")
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert len(received[0]) == 1
        item = received[0][0]
        assert isinstance(item, PreviewItem)
        assert item.aweme_id == "aweme_001"
        assert item.type == "video"

    def test_preview_failed_when_video_parser_none(self, qapp, async_worker) -> None:
        """video_parser 为 None → emit preview_failed（向后兼容）。"""
        bridge = CrawlerBridge(
            async_worker=async_worker,
            url_parser=_make_mock_url_parser(),
            user_home_crawler=MagicMock(),
            cookie_tester=MagicMock(),
            cookie_repository=_make_mock_cookie_repo(),
            worker_signals=WorkerSignals(),
            control_signals=ControlSignals(),
            video_parser=None,
        )

        failed: list[str] = []
        bridge._worker_signals.preview_failed.connect(lambda r: failed.append(r))

        bridge.on_start_parse_for_preview("https://v.douyin.com/abc/")
        time.sleep(0.3)
        qapp.processEvents()

        assert len(failed) == 1
        assert "VideoParser" in failed[0] or "未启用" in failed[0]

    def test_preview_failed_when_no_valid_cookie(self, qapp, async_worker) -> None:
        """无可用 Cookie → emit preview_failed。"""
        cookie_repo = MagicMock()
        cookie_repo.get_valid = MagicMock(return_value=None)
        bridge = _make_bridge_with_preview(qapp, async_worker, cookie_repo=cookie_repo)

        failed: list[str] = []
        bridge._worker_signals.preview_failed.connect(lambda r: failed.append(r))

        bridge.on_start_parse_for_preview("https://v.douyin.com/abc/")
        time.sleep(0.3)
        qapp.processEvents()

        assert len(failed) == 1
        assert "Cookie" in failed[0]

    def test_preview_failed_when_cookie_invalid(self, qapp, async_worker) -> None:
        """Cookie 失效（CookieInvalidError）→ emit preview_failed。"""
        video_parser = MagicMock()
        video_parser.parse_video = AsyncMock(side_effect=CookieInvalidError("Cookie 失效"))
        bridge = _make_bridge_with_preview(qapp, async_worker, video_parser=video_parser)

        failed: list[str] = []
        bridge._worker_signals.preview_failed.connect(lambda r: failed.append(r))

        bridge.on_start_parse_for_preview("https://v.douyin.com/abc/")
        time.sleep(0.3)
        qapp.processEvents()

        assert len(failed) == 1
        assert "Cookie" in failed[0]

    def test_preview_failed_when_all_lines_invalid(self, qapp, async_worker) -> None:
        """所有行解析失败 → emit preview_failed 含失败计数。"""
        url_parser = MagicMock()
        url_parser.parse = AsyncMock(side_effect=InvalidURLFormatError("无效"))
        bridge = _make_bridge_with_preview(qapp, async_worker, url_parser=url_parser)

        failed: list[str] = []
        bridge._worker_signals.preview_failed.connect(lambda r: failed.append(r))

        bridge.on_start_parse_for_preview("invalid_line_1\ninvalid_line_2")
        time.sleep(0.5)
        qapp.processEvents()

        assert len(failed) == 1
        assert "全部 2 行" in failed[0]

    def test_preview_progress_emitted_during_parse(self, qapp, async_worker) -> None:
        """多行解析过程中 parse_progress emit (current, total)。"""
        video_parser = _make_mock_video_parser()
        url_parser = MagicMock()

        async def _parse(line: str) -> ParsedURL:
            return _make_parsed_url(url=line, aweme_id=line.strip())

        url_parser.parse = AsyncMock(side_effect=_parse)
        bridge = _make_bridge_with_preview(
            qapp, async_worker, url_parser=url_parser, video_parser=video_parser
        )

        progress: list[tuple[int, int]] = []
        bridge._worker_signals.parse_progress.connect(
            lambda cur, total: progress.append((cur, total))
        )

        bridge.on_start_parse_for_preview("line1\nline2\nline3")
        time.sleep(0.6)
        qapp.processEvents()

        assert len(progress) == 3
        assert progress[0] == (1, 3)
        assert progress[2] == (3, 3)

    def test_preview_partial_failure_emits_completed(self, qapp, async_worker) -> None:
        """部分行解析失败但仍有成功项 → emit preview_completed（不 emit failed）。"""
        url_parser = MagicMock()
        call_count = [0]

        async def _parse(line: str) -> ParsedURL:
            call_count[0] += 1
            if "bad" in line:
                raise InvalidURLFormatError("无效")
            return _make_parsed_url(url=line, aweme_id=line.strip())

        url_parser.parse = AsyncMock(side_effect=_parse)
        video_parser = _make_mock_video_parser()
        bridge = _make_bridge_with_preview(
            qapp, async_worker, url_parser=url_parser, video_parser=video_parser
        )

        completed: list[list[PreviewItem]] = []
        failed: list[str] = []
        bridge._worker_signals.preview_completed.connect(lambda items: completed.append(items))
        bridge._worker_signals.preview_failed.connect(lambda r: failed.append(r))

        bridge.on_start_parse_for_preview("good1\nbad\ngood2")
        time.sleep(0.6)
        qapp.processEvents()

        assert len(failed) == 0
        assert len(completed) == 1
        assert len(completed[0]) == 2


# ==================== DB schema 迁移测试 ====================


class TestDatabaseMigrationV2:
    """v1→v2 schema 迁移测试。"""

    def test_schema_version_is_two(self) -> None:
        """SCHEMA_VERSION 常量为 2。"""
        assert SCHEMA_VERSION == 2

    def test_memory_db_has_selected_image_indices_column(
        self, memory_db: sqlite3.Connection
    ) -> None:
        """新初始化的内存 DB 含 selected_image_indices 列。"""
        assert _column_exists(memory_db, "task_items", "selected_image_indices")

    def test_v1_to_v2_migration_adds_column(self) -> None:
        """旧库（v1，无 selected_image_indices 列）迁移后含新列。"""
        # 用裸 sqlite3 连接，手动建 v1 表结构（不含 selected_image_indices）
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        # 建 v1 task_items 表（无 selected_image_indices）
        conn.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_url TEXT,
                status TEXT NOT NULL,
                total_items INTEGER DEFAULT 0,
                completed_items INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                download_dir TEXT NOT NULL
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE task_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                aweme_id TEXT,
                url TEXT NOT NULL,
                title TEXT,
                author TEXT,
                author_sec_id TEXT,
                type TEXT NOT NULL,
                duration TEXT,
                image_count INTEGER,
                cover_url TEXT,
                status TEXT NOT NULL,
                downloaded_bytes INTEGER DEFAULT 0,
                total_bytes INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                fail_reason TEXT,
                local_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """
        )
        # 写入 v1 版本记录
        conn.execute("INSERT INTO schema_version(version, applied_at) VALUES (1, '2026-07-01')")
        conn.commit()

        # 迁移前不含新列
        assert not _column_exists(conn, "task_items", "selected_image_indices")

        # 执行迁移
        migrate(conn)

        # 迁移后含新列
        assert _column_exists(conn, "task_items", "selected_image_indices")
        # schema_version 表新增 v2 记录
        rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        versions = [row["version"] for row in rows]
        assert versions == [1, 2]
        conn.close()

    def test_migration_is_idempotent(self) -> None:
        """迁移幂等：重复执行不报错。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            CREATE TABLE task_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """
        )
        conn.execute("INSERT INTO schema_version(version, applied_at) VALUES (1, '2026-07-01')")
        conn.commit()

        from app.database import _migrate_v1_to_v2

        _migrate_v1_to_v2(conn)
        # 再次调用不应抛异常
        _migrate_v1_to_v2(conn)
        assert _column_exists(conn, "task_items", "selected_image_indices")
        conn.close()


# ==================== TaskItemRepository 新方法测试 ====================


class TestTaskItemRepositorySelectedIndices:
    """TaskItemRepository 新增字段与方法测试。"""

    def test_create_with_selected_image_indices(
        self,
        task_repo: TaskRepository,
        item_repo: TaskItemRepository,
        sample_task: Task,
    ) -> None:
        """create 写入 selected_image_indices 字段。"""
        task_id = task_repo.create(sample_task)
        item = TaskItem(
            id=None,
            task_id=task_id,
            aweme_id="aweme_001",
            url="https://v.mp4",
            type="image_set",
            status="pending",
            selected_image_indices="[0,2]",
        )
        item_id = item_repo.create(item)
        loaded = item_repo.get(item_id)
        assert loaded is not None
        assert loaded.selected_image_indices == "[0,2]"

    def test_create_default_empty_selected_indices(
        self,
        task_repo: TaskRepository,
        item_repo: TaskItemRepository,
        sample_task: Task,
    ) -> None:
        """未显式设置时 selected_image_indices 默认为空字符串。"""
        task_id = task_repo.create(sample_task)
        item = TaskItem(
            id=None,
            task_id=task_id,
            aweme_id="aweme_002",
            url="https://v.mp4",
            type="video",
            status="pending",
        )
        item_id = item_repo.create(item)
        loaded = item_repo.get(item_id)
        assert loaded is not None
        assert loaded.selected_image_indices == ""

    def test_update_selected_image_indices(
        self,
        task_repo: TaskRepository,
        item_repo: TaskItemRepository,
        sample_task: Task,
    ) -> None:
        """update_selected_image_indices 更新字段成功。"""
        task_id = task_repo.create(sample_task)
        item = TaskItem(
            id=None,
            task_id=task_id,
            aweme_id="aweme_003",
            url="https://v.mp4",
            type="image_set",
            status="pending",
        )
        item_id = item_repo.create(item)

        item_repo.update_selected_image_indices(item_id, "[1,3]")
        loaded = item_repo.get(item_id)
        assert loaded is not None
        assert loaded.selected_image_indices == "[1,3]"

        # 再次更新
        item_repo.update_selected_image_indices(item_id, "")
        loaded = item_repo.get(item_id)
        assert loaded is not None
        assert loaded.selected_image_indices == ""


# ==================== TaskItemWidget 图集进度测试 ====================


def _make_image_set_item(
    image_count: int = 9,
    status: str = "downloading",
) -> TaskItem:
    """构造图集类型 TaskItem。"""
    return TaskItem(
        id=1,
        task_id=1,
        aweme_id="aweme_img",
        url="https://img1.jpg\nhttps://img2.jpg",
        title="图集作品",
        author="作者A",
        type="image_set",
        duration=None,
        image_count=image_count,
        cover_url=None,
        status=status,
        downloaded_bytes=0,
        total_bytes=0,
    )


class TestTaskItemWidgetImageSetProgress:
    """TaskItemWidget 图集类型进度显示测试。"""

    def test_image_set_shows_downloaded_count_format(self, qapp) -> None:
        """图集类型 update_progress 显示 '已下载 M/N 张'。"""
        item = _make_image_set_item(image_count=9, status="downloading")
        widget = TaskItemWidget(item)
        widget.update_progress(3, 9)
        assert widget._percent_label.text() == "已下载 3/9 张"
        # 进度条按比例
        assert widget._progress_bar.value() == 33
        widget.deleteLater()

    def test_image_set_zero_total_shows_waiting(self, qapp) -> None:
        """图集类型 total=0 显示 '等待中'。"""
        item = _make_image_set_item(image_count=9, status="downloading")
        widget = TaskItemWidget(item)
        widget.update_progress(0, 0)
        assert widget._percent_label.text() == "等待中"
        widget.deleteLater()

    def test_image_set_full_completed_shows_full_count(self, qapp) -> None:
        """图集全部完成 M=N 时显示 '已下载 N/N 张'。"""
        item = _make_image_set_item(image_count=5, status="downloading")
        widget = TaskItemWidget(item)
        widget.update_progress(5, 5)
        assert widget._percent_label.text() == "已下载 5/5 张"
        assert widget._progress_bar.value() == 100
        widget.deleteLater()

    def test_video_type_shows_percent_format(self, qapp) -> None:
        """视频类型仍显示百分比格式。"""
        item = TaskItem(
            id=1,
            task_id=1,
            aweme_id="aweme_v",
            url="https://v.mp4",
            title="视频",
            type="video",
            duration="00:15",
            status="downloading",
            downloaded_bytes=0,
            total_bytes=1024000,
        )
        widget = TaskItemWidget(item)
        widget.update_progress(512000, 1024000)
        # 视频类型显示百分比
        assert widget._percent_label.text() == "50%"
        widget.deleteLater()

    def test_image_set_init_skips_byte_progress(self, qapp) -> None:
        """图集类型初始化（update_from_task_item）跳过字节进度上报。

        初始化时 _percent_label 文字由 update_status 设置（如 downloading 时为 None，
        保持上一次文字）。这里仅验证不会显示字节百分比。
        """
        item = _make_image_set_item(image_count=9, status="pending")
        widget = TaskItemWidget(item)
        # pending 状态 update_status 设置文字为"等待中"
        assert widget._percent_label.text() == "等待中"
        widget.deleteLater()


# ==================== PreviewItemWidget 图集勾选测试 ====================


def _make_image_set_result(
    image_urls: list[str] | None = None,
    image_count: int | None = None,
) -> dict:
    """构造图集预览结果 dict（PreviewItem.to_result_dict 格式）。"""
    urls = image_urls or [
        "https://img1.jpg",
        "https://img2.jpg",
        "https://img3.jpg",
    ]
    return {
        "aweme_id": "aweme_img",
        "title": "图集作品",
        "author": "作者A",
        "type": "image_set",
        "duration": None,
        "image_count": image_count if image_count is not None else len(urls),
        "cover_url": "https://cover.jpg",
        "image_urls": urls,
        "video_url": "",
        "author_sec_id": "sec_uid",
    }


def _make_video_result() -> dict:
    """构造视频预览结果 dict。"""
    return {
        "aweme_id": "aweme_v",
        "title": "视频作品",
        "author": "作者B",
        "type": "video",
        "duration": "00:15",
        "image_count": None,
        "cover_url": "https://cover.jpg",
        "image_urls": [],
        "video_url": "https://v.mp4",
        "author_sec_id": "sec_uid",
    }


class TestPreviewItemWidgetImageSetSelection:
    """PreviewItemWidget 图集类型勾选与展开测试。"""

    def test_image_set_expand_button_visible(self, qapp) -> None:
        """图集类型显示展开按钮。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # widget 未 show 时 isVisible() 总是 False，用 isHidden() 检查"未隐藏"
        assert widget._expand_btn.isHidden() is False
        widget.deleteLater()

    def test_video_type_expand_button_hidden(self, qapp) -> None:
        """视频类型不显示展开按钮。"""
        widget = PreviewItemWidget(_make_video_result())
        assert widget._expand_btn.isHidden() is True
        widget.deleteLater()

    def test_image_set_default_all_selected(self, qapp) -> None:
        """图集默认整体勾选（所有图片勾选）。"""
        widget = PreviewItemWidget(_make_image_set_result())
        assert widget.is_selected() is True
        assert widget.get_selected_image_indices_str() == ""  # 全选用空字符串
        widget.deleteLater()

    def test_image_set_partial_selection(self, qapp) -> None:
        """图集部分选择返回 JSON 数组字符串。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # 取消第 0 张
        widget._image_chks[0].setChecked(False)
        indices_str = widget.get_selected_image_indices_str()
        indices = json.loads(indices_str)
        assert indices == [1, 2]
        widget.deleteLater()

    def test_image_set_all_unchecked_clears_main_chk(self, qapp) -> None:
        """图集全不选 → 整体勾选取消。"""
        widget = PreviewItemWidget(_make_image_set_result())
        for chk in widget._image_chks:
            chk.setChecked(False)
        assert widget.is_selected() is False
        widget.deleteLater()

    def test_image_set_main_chk_toggles_all_images(self, qapp) -> None:
        """整体勾选框切换 → 同步所有图片勾选框。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # 取消整体勾选
        widget._chk.setChecked(False)
        assert all(not chk.isChecked() for chk in widget._image_chks)
        # 重新勾选整体
        widget._chk.setChecked(True)
        assert all(chk.isChecked() for chk in widget._image_chks)
        widget.deleteLater()

    def test_image_set_at_least_one_selected_keeps_main_chk(self, qapp) -> None:
        """图集至少一张勾选 → 整体勾选保持。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # 取消第 0、1 张，保留第 2 张
        widget._image_chks[0].setChecked(False)
        widget._image_chks[1].setChecked(False)
        assert widget.is_selected() is True
        widget.deleteLater()

    def test_set_selected_true_checks_all(self, qapp) -> None:
        """set_selected(True) 同步所有图片勾选框。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # 先全部取消
        for chk in widget._image_chks:
            chk.setChecked(False)
        # set_selected True
        widget.set_selected(True)
        assert widget._chk.isChecked() is True
        assert all(chk.isChecked() for chk in widget._image_chks)
        widget.deleteLater()

    def test_set_selected_false_unchecks_all(self, qapp) -> None:
        """set_selected(False) 同步取消所有图片勾选框。"""
        widget = PreviewItemWidget(_make_image_set_result())
        widget.set_selected(False)
        assert widget._chk.isChecked() is False
        assert all(not chk.isChecked() for chk in widget._image_chks)
        widget.deleteLater()

    def test_result_data_contains_selected_indices(self, qapp) -> None:
        """result_data 包含 selected_image_indices 字段。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # 全选时为空字符串
        data = widget.result_data
        assert "selected_image_indices" in data
        assert data["selected_image_indices"] == ""

        # 部分选择时为 JSON 数组
        widget._image_chks[0].setChecked(False)
        data = widget.result_data
        indices = json.loads(data["selected_image_indices"])
        assert indices == [1, 2]
        widget.deleteLater()

    def test_expand_toggle_shows_image_grid(self, qapp) -> None:
        """点击展开按钮切换图片网格显示。"""
        widget = PreviewItemWidget(_make_image_set_result())
        # 初始隐藏（widget 未 show 时 isVisible() 不可靠，用 isHidden() 判断）
        assert widget._images_widget.isHidden() is True
        # 点击展开
        widget._expand_btn.click()
        assert widget._images_widget.isHidden() is False
        assert widget._expand_btn.text() == "收起"
        # 再次点击收起
        widget._expand_btn.click()
        assert widget._images_widget.isHidden() is True
        assert widget._expand_btn.text() == "展开"
        widget.deleteLater()


class TestPreviewItemWidgetVideoType:
    """PreviewItemWidget 视频类型行为测试。"""

    def test_video_type_no_image_chks(self, qapp) -> None:
        """视频类型 _image_chks 为空列表。"""
        widget = PreviewItemWidget(_make_video_result())
        assert widget._image_chks == []
        widget.deleteLater()

    def test_video_type_get_selected_indices_str_empty(self, qapp) -> None:
        """视频类型 get_selected_image_indices_str 返回空字符串。"""
        widget = PreviewItemWidget(_make_video_result())
        assert widget.get_selected_image_indices_str() == ""
        widget.deleteLater()

    def test_video_type_is_selected_uses_main_chk(self, qapp) -> None:
        """视频类型 is_selected 返回整体勾选框状态。"""
        widget = PreviewItemWidget(_make_video_result())
        assert widget.is_selected() is False
        widget._chk.setChecked(True)
        assert widget.is_selected() is True
        widget.deleteLater()

    def test_video_type_set_selected_toggles_main_chk(self, qapp) -> None:
        """视频类型 set_selected 仅切换整体勾选框。"""
        widget = PreviewItemWidget(_make_video_result())
        widget.set_selected(True)
        assert widget._chk.isChecked() is True
        widget.set_selected(False)
        assert widget._chk.isChecked() is False
        widget.deleteLater()
