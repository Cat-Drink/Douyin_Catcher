# Tasks

## 基础设施
- [x] Task 1: 扩展 conftest.py 与更新 .gitignore：新增 `real_long_video_aweme_id` fixture，更新 `cleanup_cookie_traces` 清理新文件，将 .gitignore 的 `.test_cookie.txt` / `.test_cookie_*.txt` 规则泛化为 `.test_*.txt`
  - [ ] SubTask 1.1: 在 conftest.py 新增 `real_long_video_aweme_id` session fixture（从 `.test_long_video_aweme_id.txt` 读取）
  - [ ] SubTask 1.2: 更新 `cleanup_cookie_traces` fixture，在清理列表中添加 `_LONG_VIDEO_AWEME_ID_PATH`
  - [ ] SubTask 1.3: 更新 .gitignore，将 `.test_cookie.txt` 和 `.test_cookie_*.txt` 两行替换为 `.test_*.txt` 通配规则
  - [ ] SubTask 1.4: 验证 `pytest -m integration` 无 Cookie 时全部 skip

## v0.0.4 crawlers 层补充
- [x] Task 2: 添加长视频解析与下载 e2e（test_long_video.py）
  - [ ] SubTask 2.1: 创建 `tests/test_e2e/test_long_video.py`，测试 `URLParser.parse → VideoParser.parse_video`（验证 `type=="long_video"`）→ Scheduler 下载 → 文件落盘
  - [ ] SubTask 2.2: 依赖 `real_cookie`、`real_long_video_aweme_id`、`tmp_download_dir`、`clean_db` fixtures
  - [ ] SubTask 2.3: 提交 `test(e2e): 添加长视频解析与下载集成测试骨架`

- [x] Task 3: 添加 VideoParser 异常响应处理 e2e（test_video_parser_errors.py）
  - [ ] SubTask 3.1: 创建 `tests/test_e2e/test_video_parser_errors.py`，包含两个测试函数：`test_parse_nonexistent_aweme_id`（使用硬编码无效 ID "0"）、`test_parse_no_cookie_raises_risk_error`（空 Cookie 触发风控异常）
  - [ ] SubTask 3.2: 依赖 `real_cookie` fixture（第二个测试不需要 Cookie 但需标记 integration 保持一致）
  - [ ] SubTask 3.3: 提交 `test(e2e): 添加 VideoParser 异常响应处理集成测试骨架`

- [x] Task 4: 添加 UserHomeCrawler 分页深度与过滤 e2e（test_user_home_pagination.py）
  - [ ] SubTask 4.1: 创建 `tests/test_e2e/test_user_home_pagination.py`，包含三个测试函数：`test_user_home_pagination_has_more_termination`（验证分页终止）、`test_user_home_filter_by_date`（日期过滤）、`test_user_home_filter_by_type`（类型过滤）
  - [ ] SubTask 4.2: 依赖 `real_cookie`、`real_sec_user_id`、`clean_db` fixtures
  - [ ] SubTask 4.3: 提交 `test(e2e): 添加 UserHomeCrawler 分页与过滤集成测试骨架`

## v0.0.5 downloader 层补充
- [x] Task 5: 添加图集断点续传 e2e（test_image_set_resume.py）
  - [ ] SubTask 5.1: 创建 `tests/test_e2e/test_image_set_resume.py`，测试图集下载中断 → Scheduler.stop → 新 Scheduler → restore_pending_tasks → 继续下载 → 全部完成
  - [ ] SubTask 5.2: 依赖 `real_cookie`、`real_image_set_aweme_id`、`tmp_download_dir`、`clean_db` fixtures
  - [ ] SubTask 5.3: 提交 `test(e2e): 添加图集断点续传集成测试骨架`

## v0.0.6 worker 层 Bridge e2e
- [x] Task 6: 添加 CrawlerBridge 真实解析与主页抓取 e2e（test_crawler_bridge_e2e.py）
  - [ ] SubTask 6.1: 创建 `tests/test_e2e/test_crawler_bridge_e2e.py`，包含三个测试函数：`test_crawler_bridge_parse_e2e`（on_start_parse → 真实 URLParser.parse → 信号回调验证）、`test_crawler_bridge_home_fetch_e2e`（on_start_home_fetch → 真实 UserHomeCrawler）、`test_crawler_bridge_cookie_test_e2e`（on_test_cookie → 真实 CookieTester）
  - [ ] SubTask 6.2: 依赖 `real_cookie`、`real_aweme_id`、`real_sec_user_id`、`clean_db` fixtures，使用 `AsyncWorker` 驱动真实异步任务
  - [ ] SubTask 6.3: 提交 `test(e2e): 添加 CrawlerBridge 真实解析与主页抓取集成测试骨架`

- [x] Task 7: 添加 DownloadBridge 真实下载与暂停恢复 e2e（test_download_bridge_e2e.py）
  - [ ] SubTask 7.1: 创建 `tests/test_e2e/test_download_bridge_e2e.py`，包含两个测试函数：`test_download_bridge_download_e2e`（on_start_download → 真实 Scheduler → 文件落盘 → item_completed 信号）、`test_download_bridge_pause_resume_e2e`（on_pause_download → on_resume_download → 完成）
  - [ ] SubTask 7.2: 依赖 `real_cookie`、`real_aweme_id`、`tmp_download_dir`、`clean_db` fixtures
  - [ ] SubTask 7.3: 提交 `test(e2e): 添加 DownloadBridge 真实下载与暂停恢复集成测试骨架`

- [x] Task 8: 添加 AsyncWorker 真实线程切换 e2e（test_async_worker_e2e.py）
  - [ ] SubTask 8.1: 创建 `tests/test_e2e/test_async_worker_e2e.py`，测试 AsyncWorker 在真实 QThread 中执行异步解析任务，验证线程切换与结果回调
  - [ ] SubTask 8.2: 依赖 `real_cookie`、`real_aweme_id`、`clean_db` fixtures
  - [ ] SubTask 8.3: 提交 `test(e2e): 添加 AsyncWorker 真实线程切换集成测试骨架`

## v0.0.7-v0.0.9 UI 层 e2e
- [x] Task 9: 添加 UI FetchPage 解析流程 e2e（test_ui_fetch_flow.py）
  - [ ] SubTask 9.1: 创建 `tests/test_e2e/test_ui_fetch_flow.py`，测试 FetchPage 输入真实分享链接 → 触发解析 → 验证结果显示，使用 `qapp` fixture 创建 QApplication
  - [ ] SubTask 9.2: 依赖 `real_cookie`、`real_aweme_id`、`clean_db`、`qapp` fixtures
  - [ ] SubTask 9.3: 提交 `test(e2e): 添加 UI FetchPage 解析流程集成测试骨架`

- [x] Task 10: 添加 UI CookiePage Cookie 管理 e2e（test_ui_cookie_flow.py）
  - [ ] SubTask 10.1: 创建 `tests/test_e2e/test_ui_cookie_flow.py`，测试 CookiePage 添加 Cookie → 测试 → 验证状态显示，使用 `qapp` fixture
  - [ ] SubTask 10.2: 依赖 `real_cookie`、`clean_db`、`qapp` fixtures
  - [ ] SubTask 10.3: 提交 `test(e2e): 添加 UI CookiePage Cookie 管理集成测试骨架`

- [x] Task 11: 添加 UI DownloadPage 下载流程 e2e（test_ui_download_flow.py）
  - [ ] SubTask 11.1: 创建 `tests/test_e2e/test_ui_download_flow.py`，测试 DownloadPage 启动下载 → 进度更新 → 完成，使用 `qapp` fixture
  - [ ] SubTask 11.2: 依赖 `real_cookie`、`real_aweme_id`、`tmp_download_dir`、`clean_db`、`qapp` fixtures
  - [ ] SubTask 11.3: 提交 `test(e2e): 添加 UI DownloadPage 下载流程集成测试骨架`

## v0.1.0 补充
- [x] Task 12: 添加 Cookie 池健康检查完整流程 e2e（test_cookie_pool_health.py）
  - [ ] SubTask 12.1: 创建 `tests/test_e2e/test_cookie_pool_health.py`，测试多 Cookie 入池 → 健康检查 → 失效标记 → 轮转切换 → 下载完成
  - [ ] SubTask 12.2: 依赖 `real_cookie`、`real_aweme_id`、`tmp_download_dir`、`clean_db` fixtures
  - [ ] SubTask 12.3: 提交 `test(e2e): 添加 Cookie 池健康检查完整流程集成测试骨架`

## 最终验收
- [x] Task 13: 最终质量验收
  - [ ] SubTask 13.1: 运行 `ruff check tests/test_e2e/` 确保无 lint 错误
  - [ ] SubTask 13.2: 运行 `black --check tests/test_e2e/` 确保格式正确
  - [ ] SubTask 13.3: 运行 `pytest -m "not integration and not slow"` 确保现有 595 个单元测试不受影响
  - [ ] SubTask 13.4: 运行 `pytest -m integration --collect-only` 确认所有新增集成测试被收集且无 Cookie 时 skip
  - [ ] SubTask 13.5: 如有修复，提交 `fix: 修复集成测试骨架的 ruff 与 black 检查问题`

# Task Dependencies
- [Task 2] depends on [Task 1]（需要 real_long_video_aweme_id fixture）
- [Task 3]-[Task 12] 依赖 [Task 1]（需要 conftest 基础设施）
- [Task 6]-[Task 8]（worker 层）可并行开发，但建议按顺序提交
- [Task 9]-[Task 11]（UI 层）可并行开发，但建议按顺序提交
- [Task 13] depends on [Task 1]-[Task 12] 全部完成
