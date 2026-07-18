"""预览阶段数据模型。

v0.1.7 图文类型下载流程引入：抓取页解析后将作品信息展示给用户
勾选，PreviewItem 是预览阶段的数据载体。与 crawlers.VideoInfo 字段
相似但用途不同——PreviewItem 仅承载 UI 预览所需的字段，且为可变
dataclass 便于 UI 层更新勾选状态。
"""

from dataclasses import dataclass, field


@dataclass
class PreviewItem:
    """预览项数据，用于抓取页展示给用户选择。

    Attributes:
        aweme_id: 作品 ID
        title: 标题
        cover_url: 封面 URL
        type: 类型（"video" / "image_set" / "long_video"）
        duration: 时长字符串（如 "00:15"），图集类型为 None
        image_urls: 图片直链列表（图集类型非空，视频类型为空）
        video_url: 视频无水印直链（视频类型非空，图集类型为空）
        author: 作者昵称
        author_sec_id: 作者 sec_user_id（下载阶段重新解析时使用）
        image_count: 图片数量（图集类型为 len(image_urls)，视频类型为 None）
    """

    aweme_id: str
    title: str
    cover_url: str
    type: str
    duration: str | None = None
    image_urls: list[str] = field(default_factory=list)
    video_url: str = ""
    author: str = ""
    author_sec_id: str = ""
    image_count: int | None = None

    @classmethod
    def from_video_info(cls, video_info) -> "PreviewItem":
        """从 VideoInfo 构造 PreviewItem。

        Args:
            video_info: crawlers.video_parser.VideoInfo 实例

        Returns:
            PreviewItem 实例，image_count 自动按图集类型计算
        """
        image_urls = list(video_info.image_urls) if video_info.image_urls else []
        return cls(
            aweme_id=video_info.aweme_id,
            title=video_info.title or "",
            cover_url=video_info.cover_url or "",
            type=video_info.type,
            duration=video_info.duration,
            image_urls=image_urls,
            video_url=video_info.no_watermark_url or "",
            author=video_info.author or "",
            author_sec_id=video_info.author_sec_id or "",
            image_count=len(image_urls) if image_urls else None,
        )

    def to_result_dict(self) -> dict:
        """转换为抓取页 ResultItemWidget 所需的 dict 格式。

        保持与 v0.1.4 的 download_requested 信号载荷字段一致，
        便于复用现有 ResultItemWidget 与入队流程。
        """
        return {
            "aweme_id": self.aweme_id,
            "title": self.title,
            "author": self.author,
            "type": self.type,
            "duration": self.duration,
            "image_count": self.image_count,
            "cover_url": self.cover_url,
            # v0.1.7 新增：预览阶段已获取的直链，供 DownloadBridge 直接使用
            "image_urls": list(self.image_urls),
            "video_url": self.video_url,
            "author_sec_id": self.author_sec_id,
        }
