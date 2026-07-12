"""抖音 Web API 调用规范常量集中定义。

本模块仅定义常量与字段路径映射，不含任何业务逻辑。当抖音 API 变更
（URL 调整、参数增减、字段路径变化）时，只需修改本模块，不影响
VideoParser / UserHomeCrawler / CookieTester 的业务代码。

对应设计文档 ``docs/structure/05-接口设计文档.md`` 第 3.3、3.4、3.5、7 节
与里程碑计划 ``docs/plans/v0.0.4-视频解析与主页抓取.md`` 第 6 节。

常量分组:
    - 接口 URL 常量（6.2.1）
    - 固定请求参数常量（6.2.2）
    - 请求头常量（6.2.3）
    - 响应字段路径常量（6.2.4，detail / post 两组）
    - 验证 HTML 特征常量（6.2.5）
"""

from __future__ import annotations

# === 6.2.1 接口 URL 常量 ===

# 视频详情接口（VideoParser 使用）
AWEME_DETAIL_URL: str = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

# 主页作品列表接口（UserHomeCrawler 使用）
AWEME_POST_URL: str = "https://www.douyin.com/aweme/v1/web/aweme/post/"

# Cookie 测试推荐接口（CookieTester 主路径）
GENERAL_SEARCH_URL: str = "https://www.douyin.com/aweme/v1/web/general/search/single/"

# Cookie 测试备选接口（获取当前登录用户信息，风控更严）
USER_PROFILE_SELF_URL: str = "https://www.douyin.com/aweme/v1/web/user/profile/self/"


# === 6.2.2 固定请求参数常量 ===

# 所有抖音 Web API 接口共用的固定参数
COMMON_FIXED_PARAMS: dict[str, str] = {
    "aid": "6383",
    "device_platform": "webapp",
    "channel": "channel_pc_web",
    "version_code": "170400",
}

# post 接口每页拉取数量
POST_PAGE_SIZE: int = 20

# Cookie 测试 search 接口的固定分页参数
COOKIE_TEST_SEARCH_KEYWORD: str = "test"
COOKIE_TEST_SEARCH_COUNT: int = 10
COOKIE_TEST_SEARCH_OFFSET: int = 0


# === 6.2.3 请求头常量 ===

# 默认 User-Agent（与 crawlers.signer.DEFAULT_USER_AGENT 保持一致，
# 避免签名 UA 与请求 UA 不匹配导致签名失效）
DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 默认 Referer
DEFAULT_REFERER: str = "https://www.douyin.com/"

# 默认 Accept
DEFAULT_ACCEPT: str = "application/json, text/plain, */*"


# === 6.2.4 响应字段路径常量 ===

# ---- detail 接口字段路径（VideoParser 使用）----

FIELD_DETAIL_AWEMME_ID: str = "aweme_detail.aweme_id"
FIELD_DETAIL_DESC: str = "aweme_detail.desc"
FIELD_DETAIL_CREATE_TIME: str = "aweme_detail.create_time"
FIELD_DETAIL_DURATION: str = "aweme_detail.video.duration"
FIELD_DETAIL_AWEME_TYPE: str = "aweme_detail.aweme_type"
FIELD_DETAIL_AUTHOR_NICKNAME: str = "aweme_detail.author.nickname"
FIELD_DETAIL_AUTHOR_SEC_UID: str = "aweme_detail.author.sec_uid"
FIELD_DETAIL_PLAY_ADDR_URL_LIST: str = "aweme_detail.video.play_addr.url_list"
FIELD_DETAIL_COVER_URL_LIST: str = "aweme_detail.video.cover.url_list"
FIELD_DETAIL_IMAGES: str = "aweme_detail.images"
FIELD_DETAIL_IMAGE_URL_LIST: str = "aweme_detail.images[*].url_list"
FIELD_DETAIL_STATISTICS: str = "aweme_detail.statistics"
FIELD_DETAIL_DIGG_COUNT: str = "aweme_detail.statistics.digg_count"
FIELD_DETAIL_COMMENT_COUNT: str = "aweme_detail.statistics.comment_count"
FIELD_DETAIL_SHARE_COUNT: str = "aweme_detail.statistics.share_count"
FIELD_DETAIL_COLLECT_COUNT: str = "aweme_detail.statistics.collect_count"
FIELD_DETAIL_TEXT_EXTRA: str = "aweme_detail.text_extra"
FIELD_DETAIL_HASHTAG_NAME: str = "aweme_detail.text_extra[*].hashtag_name"

# ---- post 接口字段路径（UserHomeCrawler 使用）----

FIELD_POST_HAS_MORE: str = "has_more"
FIELD_POST_MAX_CURSOR: str = "max_cursor"
FIELD_POST_AWEME_LIST: str = "aweme_list"
FIELD_POST_AWEME_ID: str = "aweme_list[*].aweme_id"
FIELD_POST_DESC: str = "aweme_list[*].desc"
FIELD_POST_CREATE_TIME: str = "aweme_list[*].create_time"
FIELD_POST_DURATION: str = "aweme_list[*].video.duration"
FIELD_POST_AUTHOR_NICKNAME: str = "aweme_list[*].author.nickname"
FIELD_POST_AUTHOR_SEC_UID: str = "aweme_list[*].author.sec_uid"
FIELD_POST_COVER_URL_LIST: str = "aweme_list[*].video.cover.url_list"
FIELD_POST_IMAGES: str = "aweme_list[*].images"


# === 6.2.5 验证 HTML 特征常量 ===

# 滑动验证 HTML 特征字符串元组，响应文本含任一即判定为验证页。
# 注意：HttpClient 内部已用更精确的 VERIFY_HTML_MARKERS 做一次拦截，
# 此常量作为业务层的二次校验与文档化保留。
VERIFY_HTML_MARKERS: tuple[str, ...] = ("slider", "verify", "captcha")
