"""Repository 层 CRUD 测试。

覆盖 5 个 Repository 的所有方法，含断点续传查询、Cookie 池查询、去重查询、upsert 等。
"""

from __future__ import annotations

from app.models import Cookie, Metadata, Task, TaskItem


class TestTaskRepository:
    """TaskRepository 测试。"""

    def test_create_and_get(self, task_repo, sample_task: Task) -> None:
        """create 返回的 id 可用于 get 找回数据。"""
        task_id = task_repo.create(sample_task)
        assert task_id is not None and task_id > 0

        fetched = task_repo.get(task_id)
        assert fetched is not None
        assert fetched.source_type == sample_task.source_type
        assert fetched.source_url == sample_task.source_url
        assert fetched.status == sample_task.status
        assert fetched.download_dir == sample_task.download_dir
        assert fetched.created_at != ""  # Repository 应填充时间戳
        assert fetched.updated_at != ""

    def test_get_nonexistent_returns_none(self, task_repo) -> None:
        """查询不存在的 id 返回 None。"""
        assert task_repo.get(9999) is None

    def test_get_by_status(self, task_repo, sample_task: Task) -> None:
        """按状态查询任务。"""
        # 插入 3 条 pending + 2 条 completed
        for _ in range(3):
            t = Task(**{**sample_task.__dict__, "id": None})
            t.status = "pending"
            task_repo.create(t)
        for _ in range(2):
            t = Task(**{**sample_task.__dict__, "id": None})
            t.status = "completed"
            task_repo.create(t)

        pending = task_repo.get_by_status("pending")
        completed = task_repo.get_by_status("completed")
        assert len(pending) == 3
        assert len(completed) == 2

    def test_update_status(self, task_repo, sample_task: Task) -> None:
        """更新后 get 反映新状态。"""
        task_id = task_repo.create(sample_task)
        task_repo.update_status(task_id, "downloading")

        fetched = task_repo.get(task_id)
        assert fetched is not None
        assert fetched.status == "downloading"

    def test_update_progress(self, task_repo, sample_task: Task) -> None:
        """更新 completed_items 和 total_items。"""
        task_id = task_repo.create(sample_task)
        task_repo.update_progress(task_id, completed_items=5, total_items=10)

        fetched = task_repo.get(task_id)
        assert fetched is not None
        assert fetched.completed_items == 5
        assert fetched.total_items == 10

    def test_update_progress_partial(self, task_repo, sample_task: Task) -> None:
        """total_items=None 时只更新 completed_items。"""
        task_id = task_repo.create(sample_task)
        # 先设置 total_items=10
        task_repo.update_progress(task_id, completed_items=3, total_items=10)
        # 再只更新 completed_items
        task_repo.update_progress(task_id, completed_items=5, total_items=None)

        fetched = task_repo.get(task_id)
        assert fetched is not None
        assert fetched.completed_items == 5
        assert fetched.total_items == 10  # 保留原值

    def test_delete(self, task_repo, sample_task: Task) -> None:
        """删除后 get 返回 None。"""
        task_id = task_repo.create(sample_task)
        task_repo.delete(task_id)
        assert task_repo.get(task_id) is None

    def test_get_pending_for_resume(self, task_repo, sample_task: Task) -> None:
        """返回 pending/downloading/paused 任务，不含 completed/failed。"""
        statuses = ["pending", "downloading", "paused", "completed", "failed"]
        for status in statuses:
            t = Task(**{**sample_task.__dict__, "id": None})
            t.status = status
            task_repo.create(t)

        pending = task_repo.get_pending_for_resume()
        # 应返回 3 条（pending + downloading + paused）
        assert len(pending) == 3
        result_statuses = {t.status for t in pending}
        assert result_statuses == {"pending", "downloading", "paused"}
        assert "completed" not in result_statuses
        assert "failed" not in result_statuses


class TestTaskItemRepository:
    """TaskItemRepository 测试。"""

    def test_create_and_get(self, item_repo, sample_task_item: TaskItem) -> None:
        """create 返回的 id 可用于 get 找回数据。"""
        item_id = item_repo.create(sample_task_item)
        assert item_id is not None and item_id > 0

        fetched = item_repo.get(item_id)
        assert fetched is not None
        assert fetched.task_id == sample_task_item.task_id
        assert fetched.aweme_id == sample_task_item.aweme_id
        assert fetched.url == sample_task_item.url
        assert fetched.title == sample_task_item.title
        assert fetched.type == sample_task_item.type
        assert fetched.created_at != ""

    def test_get_nonexistent_returns_none(self, item_repo) -> None:
        """查询不存在的 id 返回 None。"""
        assert item_repo.get(9999) is None

    def test_get_by_task(self, item_repo, sample_task_item: TaskItem) -> None:
        """同一 task 多个 item，按 task_id 查询返回全部。"""
        task_id = sample_task_item.task_id
        # 插入 3 条
        for i in range(3):
            item = TaskItem(**{**sample_task_item.__dict__, "id": None})
            item.aweme_id = f"aweme_{i:03d}"
            item_repo.create(item)

        items = item_repo.get_by_task(task_id)
        assert len(items) == 3

    def test_get_by_status(self, item_repo, sample_task_item: TaskItem) -> None:
        """按状态查询任务项。"""
        for status in ["pending", "downloading", "completed"]:
            item = TaskItem(**{**sample_task_item.__dict__, "id": None})
            item.aweme_id = f"aweme_{status}"
            item.status = status
            item_repo.create(item)

        pending = item_repo.get_by_status("pending")
        downloading = item_repo.get_by_status("downloading")
        completed = item_repo.get_by_status("completed")
        assert len(pending) == 1
        assert len(downloading) == 1
        assert len(completed) == 1

    def test_update_status(self, item_repo, sample_task_item: TaskItem) -> None:
        """更新状态。"""
        item_id = item_repo.create(sample_task_item)
        item_repo.update_status(item_id, "downloading")

        fetched = item_repo.get(item_id)
        assert fetched is not None
        assert fetched.status == "downloading"

    def test_update_status_with_fail_reason(self, item_repo, sample_task_item: TaskItem) -> None:
        """更新状态并记录失败原因。"""
        item_id = item_repo.create(sample_task_item)
        item_repo.update_status(item_id, "failed", fail_reason="网络超时")

        fetched = item_repo.get(item_id)
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.fail_reason == "网络超时"

    def test_update_bytes(self, item_repo, sample_task_item: TaskItem) -> None:
        """更新 downloaded_bytes 和 total_bytes。"""
        item_id = item_repo.create(sample_task_item)
        item_repo.update_bytes(item_id, downloaded_bytes=512000, total_bytes=1024000)

        fetched = item_repo.get(item_id)
        assert fetched is not None
        assert fetched.downloaded_bytes == 512000
        assert fetched.total_bytes == 1024000

    def test_update_bytes_partial(self, item_repo, sample_task_item: TaskItem) -> None:
        """total_bytes=None 时只更新 downloaded_bytes。"""
        item_id = item_repo.create(sample_task_item)
        # 先设置 total_bytes=1024000
        item_repo.update_bytes(item_id, downloaded_bytes=0, total_bytes=1024000)
        # 再只更新 downloaded_bytes
        item_repo.update_bytes(item_id, downloaded_bytes=512000, total_bytes=None)

        fetched = item_repo.get(item_id)
        assert fetched is not None
        assert fetched.downloaded_bytes == 512000
        assert fetched.total_bytes == 1024000  # 保留原值

    def test_update_retry(self, item_repo, sample_task_item: TaskItem) -> None:
        """更新重试次数。"""
        item_id = item_repo.create(sample_task_item)
        item_repo.update_retry(item_id, 2)

        fetched = item_repo.get(item_id)
        assert fetched is not None
        assert fetched.retry_count == 2

    def test_delete(self, item_repo, sample_task_item: TaskItem) -> None:
        """删除任务项。"""
        item_id = item_repo.create(sample_task_item)
        item_repo.delete(item_id)
        assert item_repo.get(item_id) is None

    def test_get_by_aweme_id(self, item_repo, sample_task_item: TaskItem) -> None:
        """按 aweme_id 查询能查到已存在项。"""
        item_repo.create(sample_task_item)
        fetched = item_repo.get_by_aweme_id(sample_task_item.aweme_id)
        assert fetched is not None
        assert fetched.aweme_id == sample_task_item.aweme_id

    def test_get_by_aweme_id_nonexistent(self, item_repo) -> None:
        """未插入的 aweme_id 返回 None。"""
        assert item_repo.get_by_aweme_id("nonexistent_aweme") is None

    def test_get_by_aweme_id_dedup(self, item_repo, sample_task_item: TaskItem) -> None:
        """同 aweme_id 多条记录返回最新一条（ORDER BY id DESC）。"""
        # 插入第一条
        first_id = item_repo.create(sample_task_item)
        # 插入第二条（同 aweme_id，不同 url）
        second_item = TaskItem(**{**sample_task_item.__dict__, "id": None})
        second_item.url = "https://example.com/video_v2.mp4"
        second_id = item_repo.create(second_item)

        fetched = item_repo.get_by_aweme_id(sample_task_item.aweme_id)
        assert fetched is not None
        assert fetched.id == second_id  # 返回最新的
        assert fetched.id != first_id

    def test_reset_downloading_to_paused(self, item_repo, sample_task_item: TaskItem) -> None:
        """3 个 downloading + 2 个 pending，执行后 downloading 变 paused。

        返回 3，pending 不受影响。
        """
        # 3 个 downloading
        for i in range(3):
            item = TaskItem(**{**sample_task_item.__dict__, "id": None})
            item.aweme_id = f"aweme_dl_{i}"
            item.status = "downloading"
            item_repo.create(item)
        # 2 个 pending
        for i in range(2):
            item = TaskItem(**{**sample_task_item.__dict__, "id": None})
            item.aweme_id = f"aweme_pd_{i}"
            item.status = "pending"
            item_repo.create(item)

        reset_count = item_repo.reset_downloading_to_paused()
        assert reset_count == 3

        # 验证状态
        paused_items = item_repo.get_by_status("paused")
        pending_items = item_repo.get_by_status("pending")
        downloading_items = item_repo.get_by_status("downloading")
        assert len(paused_items) == 3
        assert len(pending_items) == 2  # pending 不受影响
        assert len(downloading_items) == 0


class TestCookieRepository:
    """CookieRepository 测试。"""

    def _make_cookie(
        self,
        content: str = "cookie_content",
        status: str = "untested",
        last_used: str | None = None,
        fail_count: int = 0,
    ) -> Cookie:
        return Cookie(
            id=None,
            content=content,
            label="测试Cookie",
            status=status,
            last_used=last_used,
            last_check=None,
            fail_count=fail_count,
        )

    def test_add_and_get_by_id(self, cookie_repo) -> None:
        """add 后 get_by_id 返回相同数据。"""
        cookie_id = cookie_repo.add(self._make_cookie(content="test_cookie_123"))
        assert cookie_id > 0

        fetched = cookie_repo.get_by_id(cookie_id)
        assert fetched is not None
        assert fetched.content == "test_cookie_123"
        assert fetched.status == "untested"
        assert fetched.created_at != ""

    def test_remove(self, cookie_repo) -> None:
        """删除后 get_by_id 返回 None。"""
        cookie_id = cookie_repo.add(self._make_cookie())
        cookie_repo.remove(cookie_id)
        assert cookie_repo.get_by_id(cookie_id) is None

    def test_get_valid_returns_oldest(self, cookie_repo) -> None:
        """插入 3 条 valid（last_used 不同），返回最早的那条。"""
        # 注意：时间字符串需保证排序正确，用 ISO8601 但精简
        cookie_repo.add(
            self._make_cookie(content="cookie_1", status="valid", last_used="2026-01-01T10:00:00")
        )
        cookie_repo.add(
            self._make_cookie(content="cookie_2", status="valid", last_used="2026-01-01T08:00:00")
        )
        cookie_repo.add(
            self._make_cookie(content="cookie_3", status="valid", last_used="2026-01-01T12:00:00")
        )

        fetched = cookie_repo.get_valid()
        assert fetched is not None
        assert fetched.content == "cookie_2"  # last_used 最早的

    def test_get_valid_null_last_used_first(self, cookie_repo) -> None:
        """last_used 为 NULL 的优先返回。"""
        # 插入一条 last_used 不为空的 valid
        cookie_repo.add(
            self._make_cookie(
                content="cookie_with_time",
                status="valid",
                last_used="2026-01-01T08:00:00",
            )
        )
        # 插入一条 last_used 为 NULL 的 valid
        cookie_repo.add(self._make_cookie(content="cookie_null_time", status="valid"))

        fetched = cookie_repo.get_valid()
        assert fetched is not None
        assert fetched.content == "cookie_null_time"  # NULL 优先

    def test_get_valid_none_when_all_invalid(self, cookie_repo) -> None:
        """全部 invalid 时返回 None。"""
        cookie_repo.add(self._make_cookie(status="invalid"))
        cookie_repo.add(self._make_cookie(status="invalid"))
        assert cookie_repo.get_valid() is None

    def test_get_valid_none_when_empty(self, cookie_repo) -> None:
        """空池时返回 None。"""
        assert cookie_repo.get_valid() is None

    def test_update_status(self, cookie_repo) -> None:
        """更新 Cookie 状态。"""
        cookie_id = cookie_repo.add(self._make_cookie(status="untested"))
        cookie_repo.update_status(cookie_id, "valid")

        fetched = cookie_repo.get_by_id(cookie_id)
        assert fetched is not None
        assert fetched.status == "valid"

    def test_update_fail_count(self, cookie_repo) -> None:
        """更新连续失败次数。"""
        cookie_id = cookie_repo.add(self._make_cookie())
        cookie_repo.update_fail_count(cookie_id, 3)

        fetched = cookie_repo.get_by_id(cookie_id)
        assert fetched is not None
        assert fetched.fail_count == 3

    def test_update_last_used(self, cookie_repo) -> None:
        """更新最后使用时间。"""
        cookie_id = cookie_repo.add(self._make_cookie())
        cookie_repo.update_last_used(cookie_id, "2026-07-11T19:00:00")

        fetched = cookie_repo.get_by_id(cookie_id)
        assert fetched is not None
        assert fetched.last_used == "2026-07-11T19:00:00"

    def test_test_all(self, cookie_repo) -> None:
        """返回非 invalid 的 Cookie 列表。"""
        cookie_repo.add(self._make_cookie(content="c1", status="valid"))
        cookie_repo.add(self._make_cookie(content="c2", status="untested"))
        cookie_repo.add(self._make_cookie(content="c3", status="invalid"))

        result = cookie_repo.test_all()
        assert len(result) == 2  # valid + untested
        contents = {c.content for c in result}
        assert "c3" not in contents  # invalid 不应出现

    def test_get_all(self, cookie_repo) -> None:
        """查询所有 Cookie，按 created_at 排序。"""
        cookie_repo.add(self._make_cookie(content="c1"))
        cookie_repo.add(self._make_cookie(content="c2"))
        cookie_repo.add(self._make_cookie(content="c3"))

        result = cookie_repo.get_all()
        assert len(result) == 3


class TestConfigRepository:
    """ConfigRepository 测试。"""

    def test_get_nonexistent_returns_none(self, config_repo) -> None:
        """查询不存在的 key 返回 None。"""
        assert config_repo.get("nonexistent_key") is None

    def test_set_and_get(self, config_repo) -> None:
        """set 后 get 返回设置的值。"""
        config_repo.set("test_key", "test_value")
        assert config_repo.get("test_key") == "test_value"

    def test_set_upsert(self, config_repo) -> None:
        """对已存在 key 再次 set，值更新不报错。"""
        config_repo.set("dup_key", "value_1")
        assert config_repo.get("dup_key") == "value_1"

        config_repo.set("dup_key", "value_2")  # upsert
        assert config_repo.get("dup_key") == "value_2"

    def test_get_all(self, config_repo) -> None:
        """查询所有配置，返回字典。"""
        # 默认配置已存在 6 条
        config_repo.set("custom_key", "custom_value")
        result = config_repo.get_all()
        assert "custom_key" in result
        assert result["custom_key"] == "custom_value"
        # 默认配置仍存在
        assert "download_dir" in result
        assert "concurrency" in result

    def test_delete(self, config_repo) -> None:
        """删除配置项。"""
        config_repo.set("to_delete", "value")
        config_repo.delete("to_delete")
        assert config_repo.get("to_delete") is None

    def test_get_onboarding_done_default_false(self, config_repo) -> None:
        """默认首次引导未完成（DEFAULT_CONFIGS 中 onboarding_done='false'）。"""
        assert config_repo.get_onboarding_done() is False

    def test_set_onboarding_done_true(self, config_repo) -> None:
        """设置首次引导完成。"""
        config_repo.set_onboarding_done(True)
        assert config_repo.get_onboarding_done() is True
        assert config_repo.get("onboarding_done") == "true"

    def test_set_onboarding_done_false(self, config_repo) -> None:
        """设置首次引导未完成。"""
        config_repo.set_onboarding_done(True)
        assert config_repo.get_onboarding_done() is True
        config_repo.set_onboarding_done(False)
        assert config_repo.get_onboarding_done() is False
        assert config_repo.get("onboarding_done") == "false"


class TestMetadataRepository:
    """MetadataRepository 测试。"""

    def _make_metadata(self, task_item_id: int, aweme_id: str = "aweme_001") -> Metadata:
        return Metadata(
            id=None,
            task_item_id=task_item_id,
            aweme_id=aweme_id,
            title="测试视频标题",
            desc="这是测试视频描述",
            author="测试作者",
            author_uid="uid_001",
            publish_time="2026-07-11T12:00:00",
            like_count=100,
            comment_count=20,
            share_count=5,
            collect_count=10,
            tags='["旅行","海边"]',
            raw_json='{"key": "value"}',
        )

    def test_create_and_get(self, metadata_repo, item_repo, sample_task_item: TaskItem) -> None:
        """create 返回的 id 可用于 get 找回数据。"""
        item_id = item_repo.create(sample_task_item)
        metadata_id = metadata_repo.create(self._make_metadata(item_id))
        assert metadata_id > 0

        fetched = metadata_repo.get(metadata_id)
        assert fetched is not None
        assert fetched.task_item_id == item_id
        assert fetched.title == "测试视频标题"
        assert fetched.like_count == 100
        assert fetched.tags == '["旅行","海边"]'

    def test_get_by_task_item(self, metadata_repo, item_repo, sample_task_item: TaskItem) -> None:
        """按 task_item_id 查询元数据。"""
        item_id = item_repo.create(sample_task_item)
        metadata_repo.create(self._make_metadata(item_id))

        fetched = metadata_repo.get_by_task_item(item_id)
        assert fetched is not None
        assert fetched.task_item_id == item_id

    def test_get_nonexistent_returns_none(self, metadata_repo) -> None:
        """查询不存在的 id 返回 None。"""
        assert metadata_repo.get(9999) is None

    def test_get_by_task_item_nonexistent_returns_none(self, metadata_repo) -> None:
        """查询不存在的 task_item_id 返回 None。"""
        assert metadata_repo.get_by_task_item(9999) is None
