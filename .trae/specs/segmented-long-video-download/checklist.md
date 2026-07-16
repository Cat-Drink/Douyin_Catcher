# Checklist

## 测试超时
- [ ] `test_long_video.py` 等待循环从 120 秒增加到 300 秒
- [ ] 文件头部注释更新超时说明

## Scheduler 超时配置
- [ ] Scheduler 内部 `httpx.AsyncClient()` 配置了 connect=30s, read=60s 超时
- [ ] 新增 `DEFAULT_DOWNLOAD_CONNECT_TIMEOUT` 和 `DEFAULT_DOWNLOAD_READ_TIMEOUT` 常量
- [ ] Scheduler 单元测试验证超时配置

## 分片下载常量
- [ ] `SEGMENT_SIZE = 2 * 1024 * 1024`（2MB）
- [ ] `MAX_SEGMENTS = 8`
- [ ] `LARGE_FILE_THRESHOLD = 10 * 1024 * 1024`（10MB）
- [ ] 新常量在 `downloader/__init__.py` 中导出

## 文件大小探测
- [ ] `_get_file_size` 通过 HEAD 请求获取 Content-Length
- [ ] HEAD 请求失败（非 200）时返回 None
- [ ] HEAD 请求网络异常时返回 None（不抛异常）
- [ ] HEAD 响应无 Content-Length 时返回 None

## 分片计算
- [ ] `_calculate_segments` 返回 (start, end) 字节范围列表
- [ ] segment_count = min(ceil(total / SEGMENT_SIZE), MAX_SEGMENTS)
- [ ] 每个分片大小 = ceil(total / segment_count)
- [ ] 最后一个分片的 end = total_bytes - 1

## 分片下载核心
- [ ] `_download_segment` 使用 `Range: bytes={start+downloaded}-{end}` 请求
- [ ] 流式写入 `.part.{i}` 文件，支持 ab 续传模式
- [ ] 每个分片独立的重试逻辑（指数退避，MAX_RETRY_COUNT 上限）
- [ ] 分片收到 200 而非 206 时抛出异常触发回退
- [ ] `on_chunk` 回调上报每块字节数

## 分片编排
- [ ] `_download_segmented` 使用 `asyncio.gather` 并发下载所有分片
- [ ] 分片使用独立信号量 `asyncio.Semaphore(MAX_SEGMENTS)`，不挤占主信号量
- [ ] 主信号量在 `_download_single_file` 中 acquire 1 次（整个文件占 1 槽位）
- [ ] 聚合进度通过 `on_chunk` 回调实时上报 ProgressReporter
- [ ] 持久化进度满足 5s/1MB 间隔条件时写入 SQLite
- [ ] 任一分片重试耗尽 → 整个下载标记 failed
- [ ] CancelledError → 持久化所有分片进度 → 重抛
- [ ] 所有分片完成后调用 `_merge_segments`

## 分片合并
- [ ] `_merge_segments` 按分片序号顺序拼接 `.part.{i}` 文件
- [ ] 合并完成后删除所有 `.part.{i}` 临时文件
- [ ] 合并结果文件路径与单流下载一致

## 单文件流程集成
- [ ] `_download_single_file` 开头调用 `_get_file_size` 探测大小
- [ ] 文件 ≥ 10MB 走分片下载，< 10MB 走单流（不变）
- [ ] HEAD 失败回退单流
- [ ] 分片中收到 200 回退单流

## 断点续传
- [ ] 恢复时检查每个 `.part.{i}` 文件大小确定续传位置
- [ ] `.part.{i}` 不存在时该分片从头下载
- [ ] 暂停时各分片进度持久化到 SQLite
- [ ] 恢复后各分片独立续传

## 单元测试
- [x] `TestGetFileSize` 覆盖 HEAD 成功 / 404 / 网络异常
- [x] `TestCalculateSegments` 覆盖 12MB / 50MB / 5MB / 边界值
- [x] `TestDownloadSegment` 覆盖正常 / 续传 / 重试 / 200回退
- [x] `TestDownloadSegmented` 覆盖全量成功 / 部分失败 / 暂停续传 / 进度聚合
- [x] `TestMergeSegments` 覆盖正常合并 / 临时文件清理
- [x] `TestDownloadSingleFileSegmented` 覆盖大文件分片 / 小文件单流 / HEAD失败回退
- [x] 现有测试已补齐 HEAD 请求 mock（返回 404 以跳过分片路径，保持原测试意图）

## 质量验收
- [ ] `ruff check downloader/ tests/test_downloader.py` 无新增 warning
- [ ] `black --check downloader/ tests/test_downloader.py` 通过
- [ ] `pytest tests/test_downloader.py tests/test_scheduler.py -v` 全部通过
- [ ] 整体 `pytest` 通过，覆盖率 ≥ 80%
- [ ] 提供 Cookie 后 `pytest -m integration tests/test_e2e/test_long_video.py` 通过
