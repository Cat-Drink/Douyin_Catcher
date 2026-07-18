"""UserHomeCrawler 单元测试。

覆盖场景:
    - fetch_user_posts 分页拉取（2 页 + has_more=0 终止）
    - 类型过滤（video / image_set）
    - 数量上限截断
    - 时间段过滤（双端 / 仅起始 / 仅结束）
    - 空主页不报错
    - 进度回调触发与回调异常安全
    - HTTP 层异常传播
    - has_more=0 终止、游标未变化防死循环
    - _match_filters / _detect_type / _build_post_item / _build_post_params 纯单元测试

测试通过 AsyncMock + MagicMock 模拟 HttpClient，不打真实网络。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from crawlers import api_spec
from crawlers.exceptions import (
    CookieInvalidError,
    NetworkError,
    RateLimitedError,
    UserNotFoundError,
    VerifyRequiredError,
)
from crawlers.user_home_crawler import HomeFilters, PostItem, UserHomeCrawler

# ==================== fixtures ====================


@pytest.fixture
def mock_http_client() -> MagicMock:
    """返回 mock HttpClient，get 方法为 AsyncMock 供 await 调用。"""
    client = MagicMock(name="HttpClient")
    client.get = AsyncMock(name="HttpClient.get")
    return client


@pytest.fixture
def mock_signer() -> MagicMock:
    """返回 mock Signer（UserHomeCrawler 不直接调用，占位注入）。"""
    return MagicMock(name="Signer")


@pytest.fixture
def user_home_crawler(mock_http_client: MagicMock, mock_signer: MagicMock) -> UserHomeCrawler:
    """返回注入 mock 的 UserHomeCrawler 实例。"""
    return UserHomeCrawler(mock_http_client, mock_signer)


def _make_response(payload: dict, status_code: int = 200) -> httpx.Response:
    """构造 JSON 响应 httpx.Response。"""
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", api_spec.AWEME_POST_URL),
    )


def _make_aweme(
    aweme_id: str,
    *,
    desc: str = "title",
    duration: int | None = 15000,
    images: list | None = None,
    create_time: int = 1700000000,
    cover: str = "https://c.jpg",
) -> dict:
    """构造单条 aweme 节点。

    参数:
        aweme_id: 作品 ID。
        desc: 文案。
        duration: 视频时长（毫秒）；None 表示图集（无 video.duration）。
        images: 图集图片列表；非空则覆盖 duration 使其成为图集。
        create_time: 发布时间（Unix 秒）。
        cover: 封面 URL。
    """
    aweme = {
        "aweme_id": aweme_id,
        "desc": desc,
        "author": {"nickname": "作者A", "sec_uid": "sec_uid_author"},
        "video": {"cover": {"url_list": [cover]}},
        "create_time": create_time,
    }
    if images is not None:
        aweme["images"] = images
        # 图集也保留 video.duration=0 供 _detect_type 测试
        aweme["video"]["duration"] = 0
    else:
        aweme["video"]["duration"] = duration
    return aweme


# ==================== fetch_user_posts 主流程测试 ====================


class TestFetchUserPosts:
    """fetch_user_posts 主流程测试。"""

    async def test_fetch_posts_pagination(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """分页拉取（2 页）：第 1 页 has_more=1 + max_cursor=100，第 2 页 has_more=0。"""
        page1 = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1"), _make_aweme("2")],
                "has_more": 1,
                "max_cursor": 100,
            }
        )
        page2 = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("3")],
                "has_more": 0,
                "max_cursor": 200,
            }
        )
        mock_http_client.get.side_effect = [page1, page2]
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie")
        ]
        # 3 条全部 yield
        assert len(items) == 3
        assert [i.aweme_id for i in items] == ["1", "2", "3"]
        # 验证第二次调用使用了推进后的 max_cursor
        second_call_params = mock_http_client.get.await_args_list[1].kwargs["params"]
        assert second_call_params["max_cursor"] == "100"

    async def test_fetch_posts_type_filter_video(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """类型过滤：仅 video。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [
                    _make_aweme("v1", duration=15000),
                    _make_aweme("img1", images=[{"url_list": ["i.jpg"]}]),
                    _make_aweme("v2", duration=30000),
                ],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(type_filter="video"), "cookie"
            )
        ]
        assert [i.aweme_id for i in items] == ["v1", "v2"]
        assert all(i.type == "video" for i in items)

    async def test_fetch_posts_type_filter_image_set(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """类型过滤：仅 image_set。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [
                    _make_aweme("v1", duration=15000),
                    _make_aweme("img1", images=[{"url_list": ["i1.jpg"]}]),
                    _make_aweme("img2", images=[{"url_list": ["i2.jpg"]}]),
                ],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(type_filter="image_set"), "cookie"
            )
        ]
        assert [i.aweme_id for i in items] == ["img1", "img2"]
        assert all(i.type == "image_set" for i in items)
        assert items[0].image_count == 1

    async def test_fetch_posts_max_count(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """数量上限：max_count=2 时返回恰好 2 条（即使有更多）。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [
                    _make_aweme("1"),
                    _make_aweme("2"),
                    _make_aweme("3"),
                    _make_aweme("4"),
                ],
                "has_more": 1,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(max_count=2), "cookie"
            )
        ]
        assert len(items) == 2
        assert [i.aweme_id for i in items] == ["1", "2"]
        # 达到上限后不再调用第二页
        assert mock_http_client.get.await_count == 1

    async def test_fetch_posts_date_range(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """时间段过滤：start_date + end_date。"""
        # 1700000000 = 2023-11-14T22:13:20Z
        # 1700000100 = 2023-11-14T22:15:00Z
        # 1699000000 = 2023-11-03T00:26:40Z（早于 start）
        # 1715000000 = 2024-05-06T13:46:40Z（晚于 end）
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [
                    _make_aweme("in1", create_time=1700000000),
                    _make_aweme("out_early", create_time=1699000000),
                    _make_aweme("in2", create_time=1700000100),
                    _make_aweme("out_late", create_time=1715000000),
                ],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001",
                HomeFilters(start_date="2023-11-14", end_date="2023-11-15"),
                "cookie",
            )
        ]
        assert [i.aweme_id for i in items] == ["in1", "in2"]

    async def test_fetch_posts_start_date_only(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """仅起始日期：create_time >= start_date。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [
                    _make_aweme("early", create_time=1699000000),  # 2023-11-03
                    _make_aweme("late", create_time=1700000000),  # 2023-11-14
                ],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(start_date="2023-11-10"), "cookie"
            )
        ]
        assert [i.aweme_id for i in items] == ["late"]

    async def test_fetch_posts_end_date_only(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """仅结束日期：create_time <= end_date 23:59:59。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [
                    _make_aweme("in", create_time=1700000000),  # 2023-11-14
                    _make_aweme("out", create_time=1715000000),  # 2024-05-06
                ],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(end_date="2023-11-30"), "cookie"
            )
        ]
        assert [i.aweme_id for i in items] == ["in"]

    async def test_fetch_posts_empty_home(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """空主页：aweme_list 为空列表，返回空列表不抛异常。"""
        mock_http_client.get.return_value = _make_response(
            {"status_code": 0, "aweme_list": [], "has_more": 0, "max_cursor": 0}
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie")
        ]
        assert items == []

    async def test_fetch_posts_aweme_list_missing(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """aweme_list 字段缺失 → 视为空列表，正常结束。"""
        mock_http_client.get.return_value = _make_response(
            {"status_code": 0, "has_more": 0, "max_cursor": 0}
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie")
        ]
        assert items == []

    async def test_fetch_posts_progress_callback(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """进度回调：2 页时被调用 2 次，参数为累计抓取数。"""
        page1 = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1"), _make_aweme("2")],
                "has_more": 1,
                "max_cursor": 100,
            }
        )
        page2 = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("3")],
                "has_more": 0,
                "max_cursor": 200,
            }
        )
        mock_http_client.get.side_effect = [page1, page2]
        progress_calls: list[int] = []

        async for _ in user_home_crawler.fetch_user_posts(
            "sec001", HomeFilters(), "cookie", progress_callback=progress_calls.append
        ):
            pass
        assert progress_calls == [2, 3]  # 第 1 页 2 条，第 2 页累计 3 条

    async def test_fetch_posts_no_progress_callback(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """无回调时不报错。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1")],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(), "cookie", progress_callback=None
            )
        ]
        assert len(items) == 1

    async def test_fetch_posts_progress_callback_exception_safe(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """进度回调抛异常时不中断抓取。"""

        def bad_callback(count: int) -> None:
            raise RuntimeError("callback broken")

        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1"), _make_aweme("2")],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts(
                "sec001", HomeFilters(), "cookie", progress_callback=bad_callback
            )
        ]
        # 回调异常不影响 yield
        assert len(items) == 2

    async def test_fetch_posts_cookie_invalid(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """Cookie 失效（461 由 HttpClient 抛出）→ CookieInvalidError 传播。"""
        mock_http_client.get.side_effect = CookieInvalidError("Cookie 失效")
        with pytest.raises(CookieInvalidError):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_rate_limited(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """限流（429 由 HttpClient 抛出）→ RateLimitedError 传播。"""
        mock_http_client.get.side_effect = RateLimitedError("限流")
        with pytest.raises(RateLimitedError):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_verify_required(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """触发验证（VerifyRequiredError 由 HttpClient 抛出）→ 传播。"""
        mock_http_client.get.side_effect = VerifyRequiredError("需验证")
        with pytest.raises(VerifyRequiredError):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_network_error(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """网络异常 → NetworkError 传播。"""
        mock_http_client.get.side_effect = NetworkError("连接失败")
        with pytest.raises(NetworkError):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_user_not_found(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """用户不存在：status_code != 0 → UserNotFoundError。"""
        mock_http_client.get.return_value = _make_response(
            {"status_code": 1, "status_msg": "user not found"}
        )
        with pytest.raises(UserNotFoundError, match="user not found"):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_status_code_nonzero_no_status_msg(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """status_code != 0 且无 status_msg → 默认"未知错误"。"""
        mock_http_client.get.return_value = _make_response({"status_code": 9})
        with pytest.raises(UserNotFoundError, match="未知错误"):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_response_not_json(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """响应非 JSON → UserNotFoundError。"""
        response = MagicMock(spec=httpx.Response)
        response.json.side_effect = ValueError("not json")
        mock_http_client.get.return_value = response
        with pytest.raises(UserNotFoundError, match="非 JSON"):
            async for _ in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie"):
                pass

    async def test_fetch_posts_has_more_false_terminates(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """has_more=0 时正常终止，不再拉下一页。"""
        mock_http_client.get.return_value = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1")],
                "has_more": 0,
                "max_cursor": 100,
            }
        )
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie")
        ]
        assert len(items) == 1
        assert mock_http_client.get.await_count == 1

    async def test_fetch_posts_cursor_unchanged_terminates(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """游标未变化时终止（防死循环）：has_more=1 但 max_cursor 始终 0。"""
        page = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1")],
                "has_more": 1,
                "max_cursor": 0,  # 与初始 max_cursor 相同
            }
        )
        mock_http_client.get.return_value = page
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie")
        ]
        # 拉取一页后因游标未变化终止
        assert len(items) == 1
        assert mock_http_client.get.await_count == 1

    async def test_fetch_posts_cursor_invalid_terminates(
        self, user_home_crawler: UserHomeCrawler, mock_http_client: MagicMock
    ) -> None:
        """游标无效（None）时终止。"""
        page = _make_response(
            {
                "status_code": 0,
                "aweme_list": [_make_aweme("1")],
                "has_more": 1,
                "max_cursor": None,  # 无效游标
            }
        )
        mock_http_client.get.return_value = page
        items = [
            item
            async for item in user_home_crawler.fetch_user_posts("sec001", HomeFilters(), "cookie")
        ]
        assert len(items) == 1
        assert mock_http_client.get.await_count == 1


# ==================== _match_filters 纯单元测试 ====================


class TestMatchFilters:
    """_match_filters 过滤逻辑测试。"""

    def _make_item(
        self,
        *,
        type_: str = "video",
        create_time: str = "2023-11-14T22:13:20Z",
    ) -> PostItem:
        return PostItem(
            aweme_id="1",
            title="t",
            author="a",
            author_sec_id="s",
            cover_url="c",
            type=type_,
            create_time=create_time,
            duration="15s",
            image_count=None,
        )

    def test_match_filters_all_pass(self) -> None:
        """type_filter='all' + 无日期 → True。"""
        item = self._make_item()
        assert UserHomeCrawler._match_filters(item, HomeFilters()) is True

    def test_match_filters_type_mismatch(self) -> None:
        """类型不匹配 → False。"""
        item = self._make_item(type_="video")
        assert UserHomeCrawler._match_filters(item, HomeFilters(type_filter="image_set")) is False

    def test_match_filters_type_match(self) -> None:
        """类型匹配 → 通过类型过滤。"""
        item = self._make_item(type_="image_set")
        assert UserHomeCrawler._match_filters(item, HomeFilters(type_filter="image_set")) is True

    def test_match_filters_date_in_range(self) -> None:
        """日期在范围内 → True。"""
        item = self._make_item(create_time="2023-11-14T22:13:20Z")
        filters = HomeFilters(start_date="2023-11-14", end_date="2023-11-15")
        assert UserHomeCrawler._match_filters(item, filters) is True

    def test_match_filters_date_out_of_range_early(self) -> None:
        """日期早于 start_date → False。"""
        item = self._make_item(create_time="2023-11-03T00:00:00Z")
        filters = HomeFilters(start_date="2023-11-10")
        assert UserHomeCrawler._match_filters(item, filters) is False

    def test_match_filters_date_out_of_range_late(self) -> None:
        """日期晚于 end_date → False。"""
        item = self._make_item(create_time="2024-05-06T00:00:00Z")
        filters = HomeFilters(end_date="2023-11-30")
        assert UserHomeCrawler._match_filters(item, filters) is False

    def test_match_filters_end_date_inclusive(self) -> None:
        """end_date 当天 23:59:59 仍算在范围内。"""
        item = self._make_item(create_time="2023-11-15T23:00:00Z")
        filters = HomeFilters(end_date="2023-11-15")
        assert UserHomeCrawler._match_filters(item, filters) is True

    def test_match_filters_empty_create_time_with_date_filter(self) -> None:
        """空 create_time + 有日期过滤 → False。"""
        item = self._make_item(create_time="")
        filters = HomeFilters(start_date="2023-11-14")
        assert UserHomeCrawler._match_filters(item, filters) is False

    def test_match_filters_invalid_date_string(self) -> None:
        """无效日期字符串 → 解析失败视为不匹配。"""
        item = self._make_item(create_time="2023-11-14T22:13:20Z")
        filters = HomeFilters(start_date="invalid-date")
        # start_ts 为 None 时跳过 start 检查（视为通过），所以这里应返回 True
        assert UserHomeCrawler._match_filters(item, filters) is True


# ==================== _detect_type / _build_post_item 纯单元测试 ====================


class TestDetectType:
    """_detect_type 类型判断测试。"""

    def test_detect_type_image_set(self) -> None:
        """images 非空 → image_set。"""
        assert UserHomeCrawler._detect_type({"images": [{"url_list": ["x"]}]}) == "image_set"

    def test_detect_type_long_video(self) -> None:
        """v0.1.3：duration ≥ 1800000 毫秒（≥ 30 分钟） → long_video。"""
        assert UserHomeCrawler._detect_type({"video": {"duration": 1860000}}) == "long_video"

    def test_detect_type_video(self) -> None:
        """普通视频 → video。"""
        assert UserHomeCrawler._detect_type({"video": {"duration": 15000}}) == "video"

    def test_detect_type_empty(self) -> None:
        """空 dict → video（兜底）。"""
        assert UserHomeCrawler._detect_type({}) == "video"

    def test_detect_type_duration_exactly_threshold(self) -> None:
        """v0.1.3：duration 恰为 30 分钟（1800000 毫秒）→ 'long_video'（`>=` 阈值）。"""
        assert UserHomeCrawler._detect_type({"video": {"duration": 1800000}}) == "long_video"

    def test_detect_type_duration_below_threshold(self) -> None:
        """v0.1.3：duration 为 29 分钟（1740000 毫秒）→ 'video'。"""
        assert UserHomeCrawler._detect_type({"video": {"duration": 1740000}}) == "video"

    def test_detect_type_image_set_not_affected_by_duration(self) -> None:
        """v0.1.3：图集即使 duration ≥ 30 分钟仍为 'image_set'（图集判定优先）。"""
        aweme = {
            "images": [{"url_list": ["x"]}],
            "video": {"duration": 1800000},
        }
        assert UserHomeCrawler._detect_type(aweme) == "image_set"


class TestBuildPostItem:
    """_build_post_item 构造测试。"""

    def test_build_video_item(self) -> None:
        """普通视频 PostItem：含 duration，image_count=None。"""
        aweme = _make_aweme("1", duration=15000)
        item = UserHomeCrawler._build_post_item(aweme)
        assert item.aweme_id == "1"
        assert item.type == "video"
        assert item.duration == "15s"
        assert item.image_count is None
        assert item.cover_url == "https://c.jpg"
        assert item.create_time == "2023-11-14T22:13:20Z"

    def test_build_image_set_item(self) -> None:
        """图集 PostItem：duration=None，image_count=图片数。"""
        aweme = _make_aweme(
            "2",
            images=[{"url_list": ["i1.jpg"]}, {"url_list": ["i2.jpg"]}, {"url_list": ["i3.jpg"]}],
        )
        item = UserHomeCrawler._build_post_item(aweme)
        assert item.type == "image_set"
        assert item.duration is None
        assert item.image_count == 3

    def test_build_long_video_item(self) -> None:
        """长视频 PostItem：duration 显示为 MM:SS。"""
        # v0.1.3：长视频阈值改为 ≥ 30 分钟（1800000 毫秒）
        aweme = _make_aweme("3", duration=1800000)  # 30:00
        item = UserHomeCrawler._build_post_item(aweme)
        assert item.type == "long_video"
        assert item.duration == "30:00"

    def test_build_item_missing_cover(self) -> None:
        """封面缺失 → cover_url 为空字符串。"""
        aweme = {
            "aweme_id": "1",
            "desc": "t",
            "author": {"nickname": "a", "sec_uid": "s"},
            "video": {"duration": 15000},  # 无 cover
            "create_time": 1700000000,
        }
        item = UserHomeCrawler._build_post_item(aweme)
        assert item.cover_url == ""


# ==================== _build_post_params 纯单元测试 ====================


class TestBuildPostParams:
    """_build_post_params 参数构造测试。"""

    def test_build_params_initial_cursor(self) -> None:
        """初始游标为 0。"""
        params = UserHomeCrawler._build_post_params("sec001", 0)
        assert params["sec_user_id"] == "sec001"
        assert params["max_cursor"] == "0"
        assert params["count"] == str(api_spec.POST_PAGE_SIZE)

    def test_build_params_advanced_cursor(self) -> None:
        """推进后的游标正确传入。"""
        params = UserHomeCrawler._build_post_params("sec001", 123456)
        assert params["max_cursor"] == "123456"

    def test_build_params_contains_common_fixed(self) -> None:
        """含所有 COMMON_FIXED_PARAMS 字段。"""
        params = UserHomeCrawler._build_post_params("sec001", 0)
        for key, value in api_spec.COMMON_FIXED_PARAMS.items():
            assert params[key] == value


# ==================== _date_to_timestamp / _format_create_time 单元测试 ====================


class TestDateHelpers:
    """日期辅助方法测试。"""

    def test_date_to_timestamp_start_of_day(self) -> None:
        """start_of_day：当日 00:00:00。"""
        ts = UserHomeCrawler._date_to_timestamp("2023-11-14", end_of_day=False)
        assert ts is not None
        # 2023-11-14T00:00:00Z = 1699920000
        assert ts == 1699920000

    def test_date_to_timestamp_end_of_day(self) -> None:
        """end_of_day：当日 23:59:59。"""
        ts = UserHomeCrawler._date_to_timestamp("2023-11-14", end_of_day=True)
        assert ts is not None
        # 2023-11-14T23:59:59Z = 1700006399
        assert ts == 1700006399

    def test_date_to_timestamp_none(self) -> None:
        """None 输入 → None。"""
        assert UserHomeCrawler._date_to_timestamp(None) is None

    def test_date_to_timestamp_invalid(self) -> None:
        """无效日期 → None。"""
        assert UserHomeCrawler._date_to_timestamp("invalid") is None

    def test_format_create_time_normal(self) -> None:
        """Unix 秒正常转 ISO8601。"""
        assert UserHomeCrawler._format_create_time(1700000000) == "2023-11-14T22:13:20Z"

    def test_format_create_time_none(self) -> None:
        """None → 空字符串。"""
        assert UserHomeCrawler._format_create_time(None) == ""

    def test_format_create_time_zero(self) -> None:
        """0 → 空字符串。"""
        assert UserHomeCrawler._format_create_time(0) == ""
