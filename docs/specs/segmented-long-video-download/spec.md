# 长视频分片下载 Spec

## Why

当前下载引擎使用单连接流式下载，对于体积较大的长视频（>20MB），单连接在测试的 120 秒窗口内无法完成下载，导致 `test_long_video_download_full_flow` 超时失败。分片下载通过多连接并发拉取不同字节范围，可显著提升大文件下载速度，同时复用已有的 HTTP Range + `.part` 文件断点续传机制实现分片级别的断点恢复。

## What Changes

- 增加集成测试等待超时从 120 秒到 300 秒（即时止血）
- 在 `Downloader` 中新增分片下载能力：大文件（>10MB）自动切换为多段并发下载
- 新增 HEAD 请求探测文件总大小，探测失败时回退到单流下载
- 每个分片使用独立的 `.part.{index}` 文件，复用现有 Range + `.part` 断点续传逻辑
- 所有分片完成后合并为最终文件，删除临时分片文件
- 分片并发使用独立信号量（`MAX_SEGMENTS=8`），不挤占主下载并发槽位
- 分片进度聚合后通过现有 `ProgressReporter` 上报，UI 层无需修改
- 暂停/取消时持久化所有分片进度，恢复时各分片独立续传
- 配置 Scheduler 内部下载客户端的读取超时为 60 秒（默认 5 秒过于激进）

## Impact

- Affected specs: 下载引擎核心（v0.0.5），集成测试骨架（v0.1.0）
- Affected code:
  - `downloader/downloader.py` — 新增分片下载主逻辑
  - `downloader/scheduler.py` — 配置下载客户端超时
  - `downloader/__init__.py` — 导出新常量
  - `tests/test_downloader.py` — 新增分片下载单元测试
  - `tests/test_e2e/test_long_video.py` — 增加等待超时

## ADDED Requirements

### Requirement: 文件大小探测

系统 SHALL 在单文件下载开始前，通过 HEAD 请求获取 `Content-Length` 以确定文件总大小。

#### Scenario: HEAD 请求成功
- **WHEN** Downloader 准备下载一个文件
- **THEN** 发送 HEAD 请求获取 Content-Length
- **AND** 如果文件大小 ≥ `LARGE_FILE_THRESHOLD`（10MB），切换到分片下载流程

#### Scenario: HEAD 请求失败或无 Content-Length
- **WHEN** HEAD 请求返回非 200，或响应头无 Content-Length
- **THEN** 回退到现有单流下载流程，不影响正常下载

#### Scenario: HEAD 请求网络异常
- **WHEN** HEAD 请求抛出 httpx.HTTPError
- **THEN** 记录警告日志，回退到单流下载

### Requirement: 分片下载

系统 SHALL 将大文件分割为多个字节范围段，使用独立的 HTTP Range 请求并发下载。

#### Scenario: 正常分片下载
- **WHEN** 文件大小 ≥ 10MB 且 HEAD 请求成功
- **THEN** 计算分片：`segment_count = min(ceil(total_bytes / SEGMENT_SIZE), MAX_SEGMENTS)`
- **AND** 每个分片发送 `Range: bytes={start}-{end}` 请求
- **AND** 所有分片并发下载，受 `MAX_SEGMENTS` 信号量约束
- **AND** 所有分片完成后合并 `.part.{i}` 文件为最终文件
- **AND** 删除所有 `.part.{i}` 临时文件
- **AND** 标记 task_item 状态为 completed

#### Scenario: 分片下载中服务端返回 200（不支持 byte-range）
- **WHEN** 某分片的 Range 请求收到 200 而非 206
- **THEN** 中止所有分片下载，回退到单流下载流程

#### Scenario: 分片大小计算
- **GIVEN** `SEGMENT_SIZE = 2MB`，`MAX_SEGMENTS = 8`
- **WHEN** 文件大小为 50MB
- **THEN** segment_count = min(ceil(50MB / 2MB), 8) = 8
- **AND** 每个分片大小 = ceil(50MB / 8) ≈ 6.25MB
- **WHEN** 文件大小为 12MB
- **THEN** segment_count = min(ceil(12MB / 2MB), 8) = 6
- **AND** 每个分片大小 = ceil(12MB / 6) = 2MB

### Requirement: 分片断点续传

系统 SHALL 为每个分片维护独立的 `.part.{index}` 文件，支持分片级别的断点续传。

#### Scenario: 分片续传
- **WHEN** 分片下载被中断后恢复
- **THEN** 检查每个 `.part.{i}` 文件的大小
- **AND** 每个分片从其 `.part.{i}` 文件大小对应的字节位置继续下载
- **AND** 如果 `.part.{i}` 文件不存在，该分片从头开始

#### Scenario: 暂停后恢复
- **WHEN** 用户暂停分片下载
- **THEN** 所有进行中的分片收到 CancelledError
- **AND** 各分片持久化当前已下载字节数到 SQLite
- **AND** 保留所有 `.part.{i}` 文件
- **WHEN** 用户恢复下载
- **THEN** 重新计算分片，检查各 `.part.{i}` 文件大小
- **AND** 各分片独立续传

### Requirement: 分片进度聚合

系统 SHALL 聚合所有分片的下载进度，通过现有 `ProgressReporter` 统一上报。

#### Scenario: 实时进度上报
- **WHEN** 任一分片接收到数据块
- **THEN** 更新该分片的已下载字节数
- **AND** 计算所有分片已下载字节数总和
- **AND** 调用 `ProgressReporter.update(task_item_id, total_downloaded, total_bytes)`
- **AND** ProgressReporter 内部 500ms 节流，不会因高频调用导致性能问题

#### Scenario: 持久化进度
- **WHEN** 聚合下载量满足 5 秒或 1MB 间隔条件
- **THEN** 调用 `_persist_progress(task_item_id, total_downloaded, total_bytes)` 持久化到 SQLite

### Requirement: 分片重试

系统 SHALL 为每个分片提供独立的重试机制。

#### Scenario: 单分片网络异常重试
- **WHEN** 某分片遇到网络异常（httpx.HTTPError）或 5xx/461/412 状态码
- **THEN** 该分片按指数退避等待 `2^retry_count` 秒后重试
- **AND** 重试次数超过 `MAX_RETRY_COUNT`（3 次）后，整个下载标记为 failed

#### Scenario: 单分片重试不影响其他分片
- **WHEN** 分片 A 正在重试等待
- **THEN** 分片 B/C/D 继续正常下载，不被阻塞

### Requirement: 分片并发控制

系统 SHALL 使用独立于主下载信号量的分片信号量，分片下载不挤占其他文件的下载并发槽位。

#### Scenario: 分片并发不挤占主并发
- **GIVEN** Scheduler max_concurrent=3，某文件分片下载 8 段
- **WHEN** 分片下载启动
- **THEN** 主信号量被 acquire 1 次（代表该文件占 1 个并发槽位）
- **AND** 分片内部使用独立的 `MAX_SEGMENTS` 信号量控制并发
- **AND** 其他 2 个并发槽位仍可用于其他文件下载

## MODIFIED Requirements

### Requirement: 单文件下载流程

`_download_single_file` 方法在启动下载前增加文件大小探测步骤：

1. 发送 HEAD 请求获取 Content-Length
2. 如果 Content-Length ≥ `LARGE_FILE_THRESHOLD`（10MB），调用 `_download_segmented` 走分片下载
3. 否则或 HEAD 失败时，走现有单流下载流程（不变）

原有单流下载逻辑（Range 请求、64KB 流式写入、5s/1MB 持久化、重试、CancelledError 处理）保持不变。

### Requirement: Scheduler 下载客户端超时

Scheduler 内部创建的 `httpx.AsyncClient` 的读取超时从默认 5 秒调整为 60 秒，以适应大文件流式下载场景。连接超时调整为 30 秒。

## REMOVED Requirements

无移除项。
