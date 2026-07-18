"""CrawlerBridge 单元测试。

覆盖链接解析、主页抓取、Cookie 测试、取消操作等场景。
使用 mock URLParser/UserHomeCrawler/CookieTester + 真实信号。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from crawlers.cookie_tester import CookieTestResult
from crawlers.exceptions import CookieInvalidError, InvalidURLFormatError
from crawlers.url_parser import ParsedURL
from crawlers.user_home_crawler import HomeFilters, PostItem
from worker.crawler_bridge import CrawlerBridge
from worker.signals import ControlSignals, WorkerSignals

# ==================== 辅助函数 ====================


def _make_parsed_url(
    url: str = "https://www.douyin.com/video/123",
    aweme_id: str | None = "123",
) -> ParsedURL:
    """构造 ParsedURL 实例。"""
    return ParsedURL(
        type="video",
        url=url,
        aweme_id=aweme_id,
        sec_user_id=None,
        original_text=url,
    )


def _make_post_item(aweme_id: str = "aweme_001") -> PostItem:
    """构造 PostItem 实例。"""
    return PostItem(
        aweme_id=aweme_id,
        title="测试作品",
        author="测试作者",
        author_sec_id="sec_uid_001",
        cover_url="https://example.com/cover.jpg",
        type="video",
        create_time="2026-07-11T10:00:00Z",
        duration="15s",
        image_count=None,
    )


def _make_cookie() -> MagicMock:
    """构造 mock Cookie。"""
    cookie = MagicMock()
    cookie.id = 1
    cookie.content = "ttwid=fake; msToken=fake"
    return cookie


def _make_mock_url_parser() -> MagicMock:
    """构造 mock URLParser。"""
    parser = MagicMock()
    parser.parse = AsyncMock(return_value=_make_parsed_url())
    return parser


def _make_mock_home_crawler() -> MagicMock:
    """构造 mock UserHomeCrawler。"""
    crawler = MagicMock()

    async def _async_iter(sec_user_id, filters, cookie, progress_callback=None):
        posts = [_make_post_item("p1"), _make_post_item("p2")]
        for i, post in enumerate(posts, 1):
            if progress_callback is not None:
                progress_callback(i)
            yield post

    crawler.fetch_user_posts = MagicMock(side_effect=_async_iter)
    return crawler


def _make_mock_cookie_tester() -> MagicMock:
    """构造 mock CookieTester。"""
    tester = MagicMock()
    tester.test_cookie = AsyncMock(
        return_value=CookieTestResult(is_valid=True, error_message="", user_nickname="用户A")
    )
    return tester


def _make_mock_cookie_repo() -> MagicMock:
    """构造 mock CookieRepository。"""
    repo = MagicMock()
    repo.get_valid = MagicMock(return_value=_make_cookie())
    repo.get_by_id = MagicMock(return_value=_make_cookie())
    repo.get_all = MagicMock(return_value=[_make_cookie()])
    return repo


def _make_bridge(
    qapp,
    async_worker,
    url_parser=None,
    home_crawler=None,
    cookie_tester=None,
    cookie_repo=None,
) -> CrawlerBridge:
    """构造 CrawlerBridge 实例。"""
    url_parser = url_parser or _make_mock_url_parser()
    home_crawler = home_crawler or _make_mock_home_crawler()
    cookie_tester = cookie_tester or _make_mock_cookie_tester()
    cookie_repo = cookie_repo or _make_mock_cookie_repo()
    worker_signals = WorkerSignals()
    control_signals = ControlSignals()
    return CrawlerBridge(
        async_worker=async_worker,
        url_parser=url_parser,
        user_home_crawler=home_crawler,
        cookie_tester=cookie_tester,
        cookie_repository=cookie_repo,
        worker_signals=worker_signals,
        control_signals=control_signals,
    )


# ==================== 链接解析测试 ====================


class TestParse:
    """链接解析桥接测试。"""

    def test_start_parse_emits_parse_completed(self, qapp, async_worker) -> None:
        """url_parser.parse 返回结果 → parse_completed emit 结果列表。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[list] = []
        bridge._worker_signals.parse_completed.connect(lambda results: received.append(results))

        bridge.on_start_parse("https://www.douyin.com/video/123")
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert len(received[0]) == 1

    def test_start_parse_emits_parse_progress(self, qapp, async_worker) -> None:
        """多链接解析过程中 parse_progress emit (current, total)。"""
        bridge = _make_bridge(qapp, async_worker)

        progress: list[tuple[int, int]] = []
        bridge._worker_signals.parse_progress.connect(
            lambda cur, total: progress.append((cur, total))
        )

        bridge.on_start_parse("https://www.douyin.com/video/123\nhttps://www.douyin.com/video/456")
        time.sleep(0.5)
        qapp.processEvents()

        assert len(progress) == 2
        assert progress[0] == (1, 2)
        assert progress[1] == (2, 2)

    def test_start_parse_emits_parse_failed_on_exception(self, qapp, async_worker) -> None:
        """v0.1.5：单行输入且解析失败 → parse_failed emit 全部失败原因。"""
        url_parser = _make_mock_url_parser()
        url_parser.parse = AsyncMock(side_effect=InvalidURLFormatError("无效链接"))
        bridge = _make_bridge(qapp, async_worker, url_parser=url_parser)

        received: list[str] = []
        bridge._worker_signals.parse_failed.connect(lambda r: received.append(r))

        bridge.on_start_parse("invalid text")
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        # v0.1.5：单行全部失败时消息格式为 "全部 N 行链接均解析失败"
        assert "全部 1 行" in received[0]

    def test_start_parse_single_link(self, qapp, async_worker) -> None:
        """单链接文本解析正常。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[list] = []
        bridge._worker_signals.parse_completed.connect(lambda results: received.append(results))

        bridge.on_start_parse("https://www.douyin.com/video/123")
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert len(received[0]) == 1

    def test_start_parse_empty_text(self, qapp, async_worker) -> None:
        """空文本解析 → parse_completed emit 空列表。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[list] = []
        bridge._worker_signals.parse_completed.connect(lambda results: received.append(results))

        bridge.on_start_parse("")
        time.sleep(0.3)
        qapp.processEvents()

        assert len(received) == 1
        assert received[0] == []

    def test_start_parse_skips_invalid_lines(self, qapp, async_worker) -> None:
        """v0.1.5：多行混合输入（含无效行）→ 跳过无效行，parse_completed emit 有效结果。"""
        # mock url_parser.parse：第二行抛 InvalidURLFormatError
        url_parser = _make_mock_url_parser()
        call_count = [0]

        async def _parse(line):
            call_count[0] += 1
            if "invalid" in line:
                raise InvalidURLFormatError(f"无效链接: {line}")
            return _make_parsed_url(url=line, aweme_id=str(call_count[0]))

        url_parser.parse = AsyncMock(side_effect=_parse)
        bridge = _make_bridge(qapp, async_worker, url_parser=url_parser)

        received: list[list] = []
        failed: list[str] = []
        bridge._worker_signals.parse_completed.connect(lambda r: received.append(r))
        bridge._worker_signals.parse_failed.connect(lambda r: failed.append(r))

        text = "https://www.douyin.com/video/123\ninvalid line\nhttps://www.douyin.com/video/456"
        bridge.on_start_parse(text)
        time.sleep(0.5)
        qapp.processEvents()

        # 应发射 parse_completed（不发射 parse_failed）
        assert len(received) == 1
        assert len(failed) == 0
        # 2 条有效结果（跳过 invalid line）
        assert len(received[0]) == 2

    def test_start_parse_all_lines_failed_emits_parse_failed(self, qapp, async_worker) -> None:
        """v0.1.5：全部行均失败 → parse_failed emit 整体失败原因。"""
        url_parser = _make_mock_url_parser()
        url_parser.parse = AsyncMock(side_effect=InvalidURLFormatError("无效链接"))
        bridge = _make_bridge(qapp, async_worker, url_parser=url_parser)

        received: list[list] = []
        failed: list[str] = []
        bridge._worker_signals.parse_completed.connect(lambda r: received.append(r))
        bridge._worker_signals.parse_failed.connect(lambda r: failed.append(r))

        text = "invalid1\ninvalid2"
        bridge.on_start_parse(text)
        time.sleep(0.5)
        qapp.processEvents()

        # 全部失败 → parse_failed（不发射 parse_completed）
        assert len(received) == 0
        assert len(failed) == 1
        assert "2 行" in failed[0]

    def test_start_parse_mixed_valid_invalid_progress(self, qapp, async_worker) -> None:
        """v0.1.5：混合输入的 parse_progress 仍按总行数报告。"""
        url_parser = _make_mock_url_parser()

        async def _parse(line):
            if "invalid" in line:
                raise InvalidURLFormatError("无效")
            return _make_parsed_url(url=line)

        url_parser.parse = AsyncMock(side_effect=_parse)
        bridge = _make_bridge(qapp, async_worker, url_parser=url_parser)

        progress: list[tuple[int, int]] = []
        bridge._worker_signals.parse_progress.connect(
            lambda cur, total: progress.append((cur, total))
        )

        text = "https://www.douyin.com/video/1\ninvalid\nhttps://www.douyin.com/video/2"
        bridge.on_start_parse(text)
        time.sleep(0.5)
        qapp.processEvents()

        # 3 行 → 3 次 progress，total 始终为 3
        assert len(progress) == 3
        assert progress[0] == (1, 3)
        assert progress[1] == (2, 3)
        assert progress[2] == (3, 3)


# ==================== 取消解析测试 ====================


class TestCancelParse:
    """取消解析测试。"""

    def test_cancel_parse_no_error(self, qapp, async_worker) -> None:
        """cancel_parse 不报错（即使没有正在进行的解析）。"""
        bridge = _make_bridge(qapp, async_worker)

        bridge.on_cancel_parse()
        time.sleep(0.2)

        # 不应抛异常
        assert bridge._parse_task is None

    def test_new_parse_cancels_previous(self, qapp, async_worker) -> None:
        """已有解析在跑时再 start_parse → 旧任务被取消。"""
        url_parser = _make_mock_url_parser()

        async def slow_parse(text):
            await asyncio.sleep(10)
            return _make_parsed_url()

        url_parser.parse = AsyncMock(side_effect=slow_parse)
        bridge = _make_bridge(qapp, async_worker, url_parser=url_parser)

        bridge.on_start_parse("https://www.douyin.com/video/123")
        time.sleep(0.3)

        first_task = bridge._parse_task
        assert first_task is not None

        bridge.on_start_parse("https://www.douyin.com/video/456")
        time.sleep(0.3)

        # 旧任务应被取消
        assert first_task.cancelled() or first_task.done()

    def test_cancel_parse_no_failed_signal(self, qapp, async_worker) -> None:
        """取消后不 emit parse_failed。"""
        url_parser = _make_mock_url_parser()

        async def slow_parse(text):
            await asyncio.sleep(10)
            return _make_parsed_url()

        url_parser.parse = AsyncMock(side_effect=slow_parse)
        bridge = _make_bridge(qapp, async_worker, url_parser=url_parser)

        failed: list[str] = []
        bridge._worker_signals.parse_failed.connect(lambda r: failed.append(r))

        bridge.on_start_parse("https://www.douyin.com/video/123")
        time.sleep(0.3)
        bridge.on_cancel_parse()
        time.sleep(0.3)
        qapp.processEvents()

        assert len(failed) == 0


# ==================== 主页抓取测试 ====================


class TestHomeFetch:
    """主页抓取桥接测试。"""

    def test_start_home_fetch_emits_completed(self, qapp, async_worker) -> None:
        """fetch_user_posts 返回 posts → home_fetch_completed emit 列表。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[list] = []
        bridge._worker_signals.home_fetch_completed.connect(lambda posts: received.append(posts))

        bridge.on_start_home_fetch("sec_uid_001", {"type_filter": "all", "max_count": 0})
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert len(received[0]) == 2

    def test_start_home_fetch_emits_progress(self, qapp, async_worker) -> None:
        """progress_callback 被调用 → home_fetch_progress emit。"""
        bridge = _make_bridge(qapp, async_worker)

        progress: list[tuple[int, int]] = []
        bridge._worker_signals.home_fetch_progress.connect(
            lambda cur, total: progress.append((cur, total))
        )

        bridge.on_start_home_fetch("sec_uid_001", {})
        time.sleep(0.5)
        qapp.processEvents()

        assert len(progress) > 0

    def test_start_home_fetch_no_cookie(self, qapp, async_worker) -> None:
        """无可用 Cookie → home_fetch_failed emit。"""
        cookie_repo = _make_mock_cookie_repo()
        cookie_repo.get_valid = MagicMock(return_value=None)
        bridge = _make_bridge(qapp, async_worker, cookie_repo=cookie_repo)

        received: list[str] = []
        bridge._worker_signals.home_fetch_failed.connect(lambda r: received.append(r))

        bridge.on_start_home_fetch("sec_uid_001", {})
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert "Cookie" in received[0]

    def test_start_home_fetch_cookie_invalid(self, qapp, async_worker) -> None:
        """Cookie 失效 → home_fetch_failed emit。"""
        home_crawler = MagicMock()

        async def _fail_iter():
            raise CookieInvalidError("Cookie 失效")
            yield  # 使其成为 async generator

        home_crawler.fetch_user_posts = MagicMock(return_value=_fail_iter())
        bridge = _make_bridge(qapp, async_worker, home_crawler=home_crawler)

        received: list[str] = []
        bridge._worker_signals.home_fetch_failed.connect(lambda r: received.append(r))

        bridge.on_start_home_fetch("sec_uid_001", {})
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert "Cookie" in received[0]

    def test_start_home_fetch_emits_failed_on_exception(self, qapp, async_worker) -> None:
        """其他异常 → home_fetch_failed emit 原因。"""
        home_crawler = MagicMock()

        async def _fail_iter():
            raise RuntimeError("网络异常")
            yield

        home_crawler.fetch_user_posts = MagicMock(return_value=_fail_iter())
        bridge = _make_bridge(qapp, async_worker, home_crawler=home_crawler)

        received: list[str] = []
        bridge._worker_signals.home_fetch_failed.connect(lambda r: received.append(r))

        bridge.on_start_home_fetch("sec_uid_001", {})
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert "网络异常" in received[0]

    def test_home_fetch_filters_dict_to_dataclass(self, qapp, async_worker) -> None:
        """dict 形式 filters 正确转为 HomeFilters dataclass。"""
        home_crawler = MagicMock()

        captured_filters: list[HomeFilters] = []

        async def _check_iter(sec_user_id, filters, cookie, progress_callback=None):
            captured_filters.append(filters)
            return
            yield  # 使其成为 async generator

        home_crawler.fetch_user_posts = MagicMock(
            side_effect=lambda sid, f, c, progress_callback=None: _check_iter(
                sid, f, c, progress_callback
            )
        )
        bridge = _make_bridge(qapp, async_worker, home_crawler=home_crawler)

        bridge.on_start_home_fetch(
            "sec_uid_001",
            {"type_filter": "video", "max_count": 10, "start_date": "2026-01-01"},
        )
        time.sleep(0.5)
        qapp.processEvents()

        assert len(captured_filters) == 1
        assert captured_filters[0].type_filter == "video"
        assert captured_filters[0].max_count == 10
        assert captured_filters[0].start_date == "2026-01-01"


# ==================== 取消主页抓取测试 ====================


class TestCancelHomeFetch:
    """取消主页抓取测试。"""

    def test_cancel_home_fetch_no_error(self, qapp, async_worker) -> None:
        """cancel_home_fetch 不报错（即使没有正在进行的抓取）。"""
        bridge = _make_bridge(qapp, async_worker)

        bridge.on_cancel_home_fetch()
        time.sleep(0.2)

        assert bridge._home_fetch_task is None

    def test_cancel_home_fetch_no_failed_signal(self, qapp, async_worker) -> None:
        """取消后不 emit home_fetch_failed。"""
        home_crawler = MagicMock()

        async def _slow_iter():
            await asyncio.sleep(10)
            yield _make_post_item()

        home_crawler.fetch_user_posts = MagicMock(return_value=_slow_iter())
        bridge = _make_bridge(qapp, async_worker, home_crawler=home_crawler)

        failed: list[str] = []
        bridge._worker_signals.home_fetch_failed.connect(lambda r: failed.append(r))

        bridge.on_start_home_fetch("sec_uid_001", {})
        time.sleep(0.3)
        bridge.on_cancel_home_fetch()
        time.sleep(0.3)
        qapp.processEvents()

        assert len(failed) == 0


# ==================== Cookie 测试测试 ====================


class TestCookieTest:
    """Cookie 测试桥接测试。"""

    def test_test_cookie_emits_valid_result(self, qapp, async_worker) -> None:
        """cookie_tester 返回 valid → cookie_test_result emit (id, True, "")。"""
        bridge = _make_bridge(qapp, async_worker)

        received: list[tuple[int, bool, str]] = []
        bridge._worker_signals.cookie_test_result.connect(
            lambda cid, valid, msg: received.append((cid, valid, msg))
        )

        bridge.on_test_cookie(1)
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert received[0] == (1, True, "")

    def test_test_cookie_emits_invalid_result(self, qapp, async_worker) -> None:
        """cookie_tester 返回 invalid → cookie_test_result emit (id, False, msg)。"""
        cookie_tester = _make_mock_cookie_tester()
        cookie_tester.test_cookie = AsyncMock(
            return_value=CookieTestResult(
                is_valid=False, error_message="Cookie 失效", user_nickname=None
            )
        )
        bridge = _make_bridge(qapp, async_worker, cookie_tester=cookie_tester)

        received: list[tuple[int, bool, str]] = []
        bridge._worker_signals.cookie_test_result.connect(
            lambda cid, valid, msg: received.append((cid, valid, msg))
        )

        bridge.on_test_cookie(1)
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert received[0][1] is False
        assert "Cookie 失效" in received[0][2]

    def test_test_cookie_exception_emits_invalid(self, qapp, async_worker) -> None:
        """cookie_tester 抛异常 → cookie_test_result emit (id, False, str(e))。"""
        cookie_tester = _make_mock_cookie_tester()
        cookie_tester.test_cookie = AsyncMock(side_effect=RuntimeError("网络异常"))
        bridge = _make_bridge(qapp, async_worker, cookie_tester=cookie_tester)

        received: list[tuple[int, bool, str]] = []
        bridge._worker_signals.cookie_test_result.connect(
            lambda cid, valid, msg: received.append((cid, valid, msg))
        )

        bridge.on_test_cookie(1)
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert received[0][1] is False
        assert "网络异常" in received[0][2]

    def test_test_cookie_not_found(self, qapp, async_worker) -> None:
        """Cookie 不存在 → cookie_test_result emit (id, False, '不存在')。"""
        cookie_repo = _make_mock_cookie_repo()
        cookie_repo.get_by_id = MagicMock(return_value=None)
        bridge = _make_bridge(qapp, async_worker, cookie_repo=cookie_repo)

        received: list[tuple[int, bool, str]] = []
        bridge._worker_signals.cookie_test_result.connect(
            lambda cid, valid, msg: received.append((cid, valid, msg))
        )

        bridge.on_test_cookie(999)
        time.sleep(0.5)
        qapp.processEvents()

        assert len(received) == 1
        assert received[0] == (999, False, "Cookie 不存在")

    def test_test_all_cookies_emits_multiple_results(self, qapp, async_worker) -> None:
        """多条 Cookie → cookie_test_result emit 多次。"""
        cookie1 = _make_cookie()
        cookie1.id = 1
        cookie2 = _make_cookie()
        cookie2.id = 2
        cookie_repo = _make_mock_cookie_repo()
        cookie_repo.get_all = MagicMock(return_value=[cookie1, cookie2])
        bridge = _make_bridge(qapp, async_worker, cookie_repo=cookie_repo)

        received: list[tuple[int, bool, str]] = []
        bridge._worker_signals.cookie_test_result.connect(
            lambda cid, valid, msg: received.append((cid, valid, msg))
        )

        bridge.on_test_all_cookies()
        time.sleep(1.0)
        qapp.processEvents()

        assert len(received) == 2
        assert received[0][0] == 1
        assert received[1][0] == 2
