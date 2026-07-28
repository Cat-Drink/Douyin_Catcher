# Checklist

## 基础设施
- [x] conftest.py 新增 `real_long_video_aweme_id` session fixture，从 `.test_long_video_aweme_id.txt` 读取
- [x] `cleanup_cookie_traces` fixture 的清理列表包含 `_LONG_VIDEO_AWEME_ID_PATH`
- [x] .gitignore 使用 `.test_*.txt` 通配规则排除所有测试数据文件
- [x] `pytest -m integration` 无 Cookie 时全部新增测试 skip，不报错

## v0.0.4 crawlers 层补充
- [x] test_long_video.py 存在且包含 `test_long_video_download_full_flow` 测试函数
- [x] test_long_video.py 验证 `VideoParser.parse_video` 返回 `type=="long_video"`
- [x] test_long_video.py 验证 Scheduler 下载后文件落盘
- [x] test_video_parser_errors.py 存在且包含异常响应处理测试函数
- [x] test_video_parser_errors.py 验证无效 aweme_id 触发异常
- [x] test_user_home_pagination.py 存在且包含分页与过滤测试函数
- [x] test_user_home_pagination.py 验证分页终止（has_more=False）
- [x] test_user_home_pagination.py 验证日期/类型过滤生效

## v0.0.5 downloader 层补充
- [x] test_image_set_resume.py 存在且包含 `test_image_set_resume_after_interrupt` 测试函数
- [x] test_image_set_resume.py 验证图集下载中断后恢复，所有图片最终完成

## v0.0.6 worker 层 e2e
- [x] test_crawler_bridge_e2e.py 存在且包含解析、主页抓取、Cookie 测试三个测试函数
- [x] test_crawler_bridge_e2e.py 验证 CrawlerBridge 信号正确 emit
- [x] test_download_bridge_e2e.py 存在且包含下载、暂停恢复两个测试函数
- [x] test_download_bridge_e2e.py 验证 DownloadBridge 信号正确 emit 与文件落盘
- [x] test_async_worker_e2e.py 存在且包含 `test_async_worker_real_thread_e2e` 测试函数
- [x] test_async_worker_e2e.py 验证 AsyncWorker 在真实 QThread 中执行异步任务

## v0.0.7-v0.0.9 UI 层 e2e
- [x] test_ui_fetch_flow.py 存在且包含 `test_ui_fetch_page_parse_e2e` 测试函数
- [x] test_ui_fetch_flow.py 使用 `qapp` fixture 创建 QApplication
- [x] test_ui_cookie_flow.py 存在且包含 `test_ui_cookie_page_test_e2e` 测试函数
- [x] test_ui_cookie_flow.py 验证 CookiePage 添加/测试/状态显示流程
- [x] test_ui_download_flow.py 存在且包含 `test_ui_download_page_flow_e2e` 测试函数
- [x] test_ui_download_flow.py 验证 DownloadPage 下载/进度/完成流程

## v0.1.0 补充
- [x] test_cookie_pool_health.py 存在且包含 `test_cookie_pool_health_check_full_flow` 测试函数
- [x] test_cookie_pool_health.py 验证多 Cookie 入池、健康检查、失效标记、轮转切换

## 通用质量
- [x] 所有新增测试文件使用模块级 `pytestmark = pytest.mark.integration`
- [x] 所有新增测试在无 Cookie 时自动 skip（通过 fixture 的 `pytest.skip`）
- [x] `ruff check tests/test_e2e/` 无错误
- [x] `black --check tests/test_e2e/` 无需格式化
- [x] `pytest -m "not integration and not slow"` 现有 595 个单元测试全部通过
- [x] `pytest -m integration --collect-only` 能收集所有新增集成测试（19 个）
- [x] 每个测试文件完成后有对应的细粒度 git commit（12 个 commit）
- [x] 未修改任何生产代码（仅新增测试文件与扩展 conftest/.gitignore）
- [x] 未修改 `docs/structure/` 目录下的任何文档
