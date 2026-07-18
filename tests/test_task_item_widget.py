"""TaskItemWidget 单元测试。

v0.1.4：覆盖任务行标题显示逻辑：
    - 有 title 时显示 title
    - title 为空但 aweme_id 存在时回退 "未命名 (aweme_id)"
    - 两者均空时回退 "未命名"
    - 超长标题通过 QFontMetrics.elidedText 省略

不依赖网络与真实 Bridge，使用真实 TaskItem dataclass。
"""

from __future__ import annotations

from app.models import TaskItem
from ui.widgets.task_item_widget import TaskItemWidget


def _make_item(
    *,
    aweme_id: str | None = "aweme_001",
    title: str | None = "测试视频",
    author: str | None = "测试作者",
    cover_url: str | None = None,
) -> TaskItem:
    """构造测试用 TaskItem（不写入 DB）。"""
    return TaskItem(
        id=1,
        task_id=1,
        aweme_id=aweme_id,
        url="https://example.com/v.mp4",
        title=title,
        author=author,
        author_sec_id="sec_uid_001",
        type="video",
        duration="00:15",
        image_count=None,
        cover_url=cover_url,
        status="pending",
        downloaded_bytes=0,
        total_bytes=1024000,
        retry_count=0,
        fail_reason=None,
        local_path=None,
    )


class TestTitleDisplay:
    """标题显示逻辑测试。"""

    def test_title_shown_when_present(self, qapp) -> None:
        """有 title 时 _full_title 与 _title_label 显示 title。"""
        item = _make_item(title="我的测试视频")
        widget = TaskItemWidget(item)
        assert widget._full_title == "我的测试视频"
        # widget 未布局时 width<=0，直接显示完整标题
        assert widget._title_label.text() == "我的测试视频"
        widget.deleteLater()

    def test_title_fallback_to_aweme_id(self, qapp) -> None:
        """title 为空但 aweme_id 存在时回退 "未命名 (aweme_id)"。"""
        item = _make_item(title=None, aweme_id="7000000000000000001")
        widget = TaskItemWidget(item)
        assert widget._full_title == "未命名 (7000000000000000001)"
        assert widget._title_label.text() == "未命名 (7000000000000000001)"
        widget.deleteLater()

    def test_title_fallback_to_unnamed(self, qapp) -> None:
        """title 与 aweme_id 均空时回退 "未命名"。"""
        item = _make_item(title=None, aweme_id=None)
        widget = TaskItemWidget(item)
        assert widget._full_title == "未命名"
        assert widget._title_label.text() == "未命名"
        widget.deleteLater()

    def test_title_empty_string_treated_as_missing(self, qapp) -> None:
        """title 为空字符串时视为缺失，回退到 aweme_id。"""
        item = _make_item(title="", aweme_id="aweme_xyz")
        widget = TaskItemWidget(item)
        # item.title 为空字符串时 if item.title 为 False，进入 aweme_id 分支
        assert widget._full_title == "未命名 (aweme_xyz)"
        widget.deleteLater()


class TestTitleElision:
    """标题超长省略测试。"""

    def test_elided_when_width_narrow(self, qapp) -> None:
        """窄宽度下超长标题应被省略为以 "…" 结尾。"""
        long_title = "这是一个非常非常非常非常非常非常非常非常长的视频标题" * 3
        item = _make_item(title=long_title)
        widget = TaskItemWidget(item)
        # 模拟 label 已布局：设置一个较小宽度触发省略
        widget._title_label.resize(80, 20)
        widget._apply_elided_title()
        text = widget._title_label.text()
        assert text.endswith("…"), f"期望以 … 结尾，实际: {text!r}"
        assert len(text) < len(long_title), "省略后长度应短于原始标题"
        widget.deleteLater()

    def test_full_title_shown_when_width_wide(self, qapp) -> None:
        """宽宽度下短标题应完整显示，不含 "…"。"""
        short_title = "短视频"
        item = _make_item(title=short_title)
        widget = TaskItemWidget(item)
        # 设置一个足够宽的宽度
        widget._title_label.resize(800, 20)
        widget._apply_elided_title()
        assert widget._title_label.text() == short_title
        widget.deleteLater()

    def test_resize_event_triggers_re_elide(self, qapp) -> None:
        """resizeEvent 后标题应按新宽度重新省略。"""
        long_title = "标题标题标题标题标题标题标题标题标题标题标题标题标题标题标题标题"
        item = _make_item(title=long_title)
        widget = TaskItemWidget(item)
        # 初次设置窄宽度
        widget._title_label.resize(60, 20)
        widget._apply_elided_title()
        narrow_text = widget._title_label.text()
        assert narrow_text.endswith("…")
        # 加宽后应恢复更多字符（不一定是完整，但应不同于窄版本）
        widget._title_label.resize(400, 20)
        widget._apply_elided_title()
        wide_text = widget._title_label.text()
        assert len(wide_text) > len(narrow_text)
        widget.deleteLater()


class TestMetaInfo:
    """元信息（作者·时长）显示测试。"""

    def test_meta_with_author_and_duration(self, qapp) -> None:
        """有作者和时长时显示 "作者 · 时长"。"""
        item = _make_item(author="作者A", title="t")
        widget = TaskItemWidget(item)
        assert widget._meta_label.text() == "作者A · 00:15"
        widget.deleteLater()

    def test_meta_with_image_count(self, qapp) -> None:
        """图集类型显示图片张数。"""
        item = TaskItem(
            id=1,
            task_id=1,
            aweme_id="aweme_img",
            url="",
            title="图集作品",
            author="作者B",
            type="image_set",
            duration=None,
            image_count=9,
            cover_url=None,
            status="pending",
        )
        widget = TaskItemWidget(item)
        assert widget._meta_label.text() == "作者B · 9张图"
        widget.deleteLater()
