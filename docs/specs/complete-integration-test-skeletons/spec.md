# 补齐 v0.0.4-v0.1.0 集成测试骨架 Spec

## Why
v0.1.0 里程碑已建立 10 个端到端集成测试场景（覆盖 crawlers + downloader 层），但 worker 层（v0.0.6 Bridge）和 UI 层（v0.0.7-v0.0.9）完全缺失真实环境集成测试骨架，且部分边缘场景（长视频、图集断点续传、Cookie 池健康检查完整流程、异常响应处理）未覆盖。需要补齐这些骨架，确保所有里程碑模块都有可执行的真实环境集成测试，无 Cookie 时自动 skip。

## What Changes
- 扩展 `tests/test_e2e/conftest.py`，新增 `real_long_video_aweme_id` fixture，更新 `cleanup_cookie_traces` 清理新文件
- 更新 `.gitignore`，将 `.test_cookie.txt` / `.test_cookie_*.txt` 规则泛化为 `.test_*.txt`，覆盖所有测试数据文件
- 新增 11 个端到端集成测试文件，覆盖 v0.0.4-v0.1.0 全部里程碑的缺失场景：
  - **v0.0.4 补充（3 个）**：长视频解析下载、VideoParser 异常响应、UserHomeCrawler 分页与过滤
  - **v0.0.5 补充（1 个）**：图集断点续传
  - **v0.0.6 worker 层（3 个）**：CrawlerBridge 真实解析/主页抓取/Cookie 测试、DownloadBridge 真实下载/暂停恢复、AsyncWorker 真实线程切换
  - **v0.0.7-v0.0.9 UI 层（3 个）**：FetchPage 解析流程、CookiePage Cookie 管理、DownloadPage 下载流程
  - **v0.1.0 补充（1 个）**：Cookie 池健康检查完整流程
- 所有新增测试用 `@pytest.mark.integration` 标记（通过模块级 `pytestmark`），无 Cookie 时自动 skip
- 每个测试文件完成后进行一次细粒度 git commit

## Impact
- Affected specs: v0.0.4（视频解析与主页抓取）、v0.0.5（下载引擎核心）、v0.0.6（工作线程桥接）、v0.0.7-v0.0.9（UI 层）、v0.1.0（打包发布与集成测试）
- Affected code:
  - `tests/test_e2e/conftest.py`（扩展 fixtures）
  - `.gitignore`（泛化排除规则）
  - 新增 11 个测试文件于 `tests/test_e2e/` 目录
  - 不修改任何生产代码

## ADDED Requirements

### Requirement: 集成测试骨架覆盖全部里程碑模块
系统 SHALL 为 v0.0.4 到 v0.1.0 的每个里程碑模块提供至少一个真实环境集成测试骨架，覆盖该里程碑的核心功能点。

#### Scenario: 无 Cookie 时自动跳过
- **WHEN** 运行 `pytest -m integration` 且未配置 `.test_cookie.txt`
- **THEN** 所有新增集成测试自动 skip，不报错

#### Scenario: 有 Cookie 时执行真实流程
- **WHEN** 运行 `pytest -m integration` 且已配置所需 `.test_*.txt` 文件
- **THEN** 对应的集成测试执行真实 API 调用与文件下载，验证端到端流程

### Requirement: worker 层 Bridge 端到端集成测试
系统 SHALL 为 `CrawlerBridge`、`DownloadBridge`、`AsyncWorker` 提供真实环境集成测试骨架，验证 Bridge → 真实爬虫/下载引擎 → 真实 API/文件系统的完整链路。

#### Scenario: CrawlerBridge 真实解析
- **WHEN** 通过 `CrawlerBridge.on_start_parse` 触发真实 URLParser.parse
- **THEN** 解析成功后 emit `parse_completed` 信号，携带正确的 aweme_id

#### Scenario: DownloadBridge 真实下载
- **WHEN** 通过 `DownloadBridge.on_start_download` 触发真实 Scheduler 下载
- **THEN** 下载完成后 emit `item_completed` 信号，文件落盘

### Requirement: UI 层关键路径端到端集成测试
系统 SHALL 为 FetchPage、CookiePage、DownloadPage 提供真实环境集成测试骨架，验证 UI 组件 → Bridge → 真实爬虫/下载引擎的完整链路。

#### Scenario: FetchPage 解析流程
- **WHEN** 在 FetchPage 输入真实分享链接并触发解析
- **THEN** 解析完成后 UI 显示正确的视频信息

#### Scenario: CookiePage Cookie 测试流程
- **WHEN** 在 CookiePage 添加真实 Cookie 并触发测试
- **THEN** 测试完成后 UI 显示 Cookie 有效状态

### Requirement: 边缘场景集成测试
系统 SHALL 为长视频、图集断点续传、Cookie 池健康检查完整流程、VideoParser 异常响应提供集成测试骨架。

#### Scenario: 长视频解析与下载
- **WHEN** 解析一个长视频类型的 aweme_id
- **THEN** VideoParser 返回 `type=="long_video"`，Scheduler 下载成功

#### Scenario: 图集断点续传
- **WHEN** 图集下载中断后通过新 Scheduler 恢复
- **THEN** 所有未完成的图片继续下载，最终全部完成

#### Scenario: Cookie 池健康检查
- **WHEN** 多个 Cookie 入池，其中一个失效
- **THEN** 健康检查标记失效 Cookie，自动切换有效 Cookie 继续下载

### Requirement: 测试数据文件安全
系统 SHALL 通过 `.gitignore` 排除所有 `.test_*.txt` 文件，并在测试 session 结束后自动清除。

#### Scenario: gitignore 排除规则
- **WHEN** 创建任何 `.test_*.txt` 文件
- **THEN** 该文件被 git 忽略，不会入库

#### Scenario: session 结束自动清理
- **WHEN** 集成测试 session 结束
- **THEN** 所有 `.test_*.txt` 文件被自动删除
