### Task 3 完成报告: backend/app.py 注册 Scheduler 回调

**状态**: 完成
**时间**: 2026-08-05
**任务简报**: D:\Program\Douyin_Catcher\.superpowers\sdd\2026-08-05-issue-2-completion-progress\task-3-brief.md

---

#### 1. 实施内容

在 `backend/app.py` 的 `lifespan()` 函数中，将原本传入 `None` 的三个 Scheduler 回调参数替换为三个实际回调函数：

- `_on_item_completed(task_item_id: int)` -- 记录日志并通过 `ws_router.manager.broadcast` 发送 `{type: "item_completed", task_item_id, timestamp}` 事件
- `_on_item_failed(task_item_id: int, fail_reason: str)` -- 记录日志并通过 `ws_router.manager.broadcast` 发送 `{type: "item_failed", task_item_id, fail_reason, timestamp}` 事件
- `_on_progress(updates: list)` -- 遍历 `ProgressUpdate` 列表，按百分比计算 progress，通过 `ws_router.manager.broadcast` 发送 `{type: "progress", updates: [...], timestamp}` 事件

每个回调内部使用 `asyncio.create_task(...)` 来执行 WebSocket 广播，因为回调本身由 Scheduler 同步/异步调用，广播不应阻塞调度器主循环。

#### 2. 导入验证

- `ws_router` 已在 `app.py` 第 30 行通过 `from backend.api import ws as ws_router` 导入，符合现有 import 模式
- `ws_router.manager` 是 `backend/api/ws.py` 第 55 行定义的 `ConnectionManager` 单例，有 `broadcast(dict)` 方法
- 新增导入 `asyncio` 和 `datetime`，均为标准库，无依赖风险

#### 3. 关键设计决策

- 进度百分比计算使用 `round((downloaded_bytes / max(total_bytes, 1)) * 100, 1)` 而非 `update.progress`，因为 `ProgressUpdate` 数据类没有 `progress` 属性，只有 `task_item_id`、`downloaded_bytes`、`total_bytes`、`status` 四个字段
- 不调用 `Scheduler._sync_task_stats`，该逻辑已在 Task 2 中由 `_run_download` 在其所有退出路径上自行调用
- `_on_progress` 添加了 `if not updates: return` 空值保护

#### 4. 测试结果

运行了 `tests/test_scheduler.py` 和 `tests/test_progress_reporter.py`：

```
66 passed, 38 warnings in 13.45s
```

所有 66 个测试全部通过。warnings 均为已存在的 ResourceWarning（未关闭的 sqlite 连接等预存问题），与本 Task 改动无关。

覆盖率报告要求 80%，但当前全仓库覆盖率仅 33%（backend API 路由等未测试），这是已知的预存状况，非本 Task 引入。

#### 5. 关注点

- **asyncio.create_task 异常处理**: `_on_progress` 和两个完成回调都使用 `asyncio.create_task` 创建广播协程，但没有收集异常。如果 `manager.broadcast` 抛出异常，它会在后台静默丢失。通常这可以接受（WebSocket 断开不应阻塞下载），但长期运行中应注意日志中可能出现未处理异常告警。
- **回调为同步函数**: 三个回调均为普通同步函数（非 async），因为 Scheduler 调用它们时期望的是 `Callable[[int], None]` 等签名，内部通过 `asyncio.create_task` 创建异步广播任务。对于 `_on_progress`，`ProgressReporter.flush()` 是同步调用 `on_progress`，方案也适用。

#### 6. 修改文件

- 修改: `D:\Program\Douyin_Catcher\backend\app.py`
