# Issue 2 下载任务完成状态与进度条显示异常 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复完成状态不显示绿色、清空操作影响进行中任务、WebSocket 不推送终态导致刷新回退等问题，确保任务完成后立即稳定显示绿色 100%，清空操作仅删除已完成项且不影响进行中项。

**Architecture:** 后端补齐 Scheduler 完成/失败/进度回调，通过单一 `_sync_task_stats` 更新父任务展示统计；WebSocket 推送所有状态（含 completed/failed）并归一化完成进度为 100；API 返回完成项进度强制 100；前端 Store 合并逻辑在刷新时保护较新的实时终态不被覆盖。

**Tech Stack:** Python 3.11+, FastAPI, asyncio, WebSocket, SQLite, React, TypeScript, Zustand

## Global Constraints

- 父任务只做展示统计标记，不参与任何任务项行为决策
- 任务项暂停/恢复/重试/删除/入队去重只依据任务项自身状态与 ID
- WebSocket 推送只读数据，不修改数据库
- 前端 `loadTasks()` 不覆盖已有较新终态或更高进度
- 完成项在 API 和 WebSocket 中进度强制为 100

---

## File Map

| File | Role | Action |
|------|------|--------|
| `backend/app.py` | 创建 Scheduler 时注册回调 | Modify |
| `downloader/scheduler.py` | 增加 `_sync_task_stats` 并在 pause/resume/restore 调用；progress 回调使用 `on_progress` | Modify |
| `backend/api/download.py` | API 返回完成项进度 100；clear-completed 按 task_item 状态判断 | Modify |
| `backend/api/ws.py` | 推送所有状态（非仅 downloading），完成项进度归 100 | Modify |
| `downloader/progress_reporter.py` | ProgressUpdate 增加状态字段 | Modify |
| `frontend/src/store/taskStore.ts` | loadTasks 合并不覆盖终态；applyProgressUpdate 完成状态归 100 | Modify |
| `tests/test_scheduler.py` | 增加回调、统计同步、终态不误触测试 | Modify |
| `tests/test_api_download.py` | 增加 API 进度归一化、clear-completed 测试 | Create |
| `tests/test_ws.py` | 增加 WebSocket 推送终态测试 | Create |

---

### Task 1: ProgressUpdate 增加任务项状态字段

**Files:**
- Modify: `downloader/progress_reporter.py:ProgressUpdate` dataclass

**Interfaces:**
- Produces: `ProgressUpdate` 新增 `status: str` 字段，默认值 `"downloading"`

- [ ] **Step 1: 修改 ProgressUpdate dataclass**

```python
# downloader/progress_reporter.py

@dataclass(frozen=True)
class ProgressUpdate:
    task_item_id: int
    downloaded_bytes: int
    total_bytes: int
    progress: float
    status: str = "downloading"  # 新增：任务项状态
```

- [ ] **Step 2: 更新 Downloader._persist_progress 中创建 ProgressUpdate 的调用**

```python
# downloader/downloader.py，_persist_progress 调用处
# 在进度节流时传入当前任务项状态
self._progress_reporter.update(
    ProgressUpdate(
        task_item_id=task_item_id,
        downloaded_bytes=downloaded_bytes,
        total_bytes=total_bytes,
        progress=progress,
        status="downloading",  # 下载中进度始终为 downloading
    )
)
```

- [ ] **Step 3: 运行现有测试确保不破坏**

```bash
cd D:/Program/Douyin_Catcher && python -m pytest tests/test_progress_reporter.py tests/test_downloader.py -x -q
```

- [ ] **Step 4: Commit**

```bash
git add downloader/progress_reporter.py downloader/downloader.py
git commit -m "feat: add status field to ProgressUpdate for completion tracking"
```

---

### Task 2: Scheduler 增加 _sync_task_stats 并在回调中调用

**Files:**
- Modify: `downloader/scheduler.py`

**Interfaces:**
- Produces: `_sync_task_stats(task_id: int) -> None` — 原子化统计该任务下所有 task_items，更新父任务的 completed_items 与 status
- Consumes: `TaskRepository`, `TaskItemRepository`（已在 __init__ 中持有）

- [ ] **Step 1: 在 Scheduler.__init__ 中初始化 TaskRepository**

```python
# downloader/scheduler.py Scheduler.__init__
# 在 __init__ 中添加：
self._task_repo = TaskRepository(conn)
```

注意：需要 import TaskRepository（文件顶部已有 `from app.repositories import TaskItemRepository`，需改为 `from app.repositories import TaskItemRepository, TaskRepository`）。

- [ ] **Step 2: 实现 _sync_task_stats**

```python
# downloader/scheduler.py Scheduler 类内

def _sync_task_stats(self, task_id: int) -> None:
    """同步父任务的展示统计。
    
    从该 task 下所有 task_items 推导 completed_items 和 status，
    不修改任何 task_item 状态，仅作展示标记。
    """
    items = self._item_repo.get_by_task(task_id)
    if not items:
        return
    
    completed_count = sum(1 for it in items if it.status == "completed")
    failed_count = sum(1 for it in items if it.status == "failed")
    active_count = sum(
        1 for it in items
        if it.status in ("pending", "downloading", "paused")
    )
    
    self._task_repo.update_progress(
        task_id, completed_items=completed_count, total_items=len(items)
    )
    
    if completed_count == len(items):
        self._task_repo.update_status(task_id, "completed")
    elif active_count == 0 and failed_count > 0:
        self._task_repo.update_status(task_id, "failed")
    elif active_count > 0:
        self._task_repo.update_status(task_id, "downloading")
```

- [ ] **Step 3: 在 _run_download 中调用 _sync_task_stats**

```python
# downloader/scheduler.py _run_download 方法中

async def _run_download(self, task_item: TaskItem) -> None:
    try:
        result = await self._downloader.download(task_item)
        if result.success:
            logger.info("task_item id=%s 下载成功", task_item.id)
            # 任务项状态已由 Downloader._mark_status 设为 completed
            self._sync_task_stats(task_item.task_id)
            if self._on_item_completed is not None:
                self._on_item_completed(task_item.id)
        else:
            reason = result.error or "未知错误"
            logger.warning("task_item id=%s 下载失败: %s", task_item.id, reason)
            self._sync_task_stats(task_item.task_id)
            if self._on_item_failed is not None:
                self._on_item_failed(task_item.id, reason)
    except asyncio.CancelledError:
        logger.info("task_item id=%s 下载被取消（暂停）", task_item.id)
        # 取消时 _item_repo.update_status 已由 pause() 设置为 paused
        self._sync_task_stats(task_item.task_id)
        raise
    except Exception as e:
        logger.exception("task_item id=%s 下载异常", task_item.id)
        self._item_repo.update_status(task_item.id, "failed", fail_reason=str(e))
        self._sync_task_stats(task_item.task_id)
        if self._on_item_failed is not None:
            self._on_item_failed(task_item.id, str(e))
```

- [ ] **Step 4: 在 pause/resume/restore 中也调用 _sync_task_stats**

pause 方法最后，在 `self._item_repo.update_status(task_item_id, "paused")` 之后添加：
```python
# 获取 item 的 task_id 用于统计
item = self._item_repo.get(task_item_id)
if item is not None:
    self._sync_task_stats(item.task_id)
```

resume 方法中，重入下载队列已通过 `_run_download` 间接更新统计，但需在成功创建 asyncio.Task 后 mark downloading 并同步：
```python
async def resume(self, task_item_id: int) -> None:
    ...
    if item.status != "paused":
        ...
        return
    self._item_repo.update_status(task_item_id, "downloading")
    self._sync_task_stats(item.task_id)
    task = asyncio.create_task(self._run_download(item))
    ...
```

restore_pending_tasks 在 reset 后也需对每个任务同步：
```python
# 在 add_task_items 之前对涉及的任务同步统计
tasks_seen: set[int] = set()
for it in items:
    if it.task_id not in tasks_seen:
        self._sync_task_stats(it.task_id)
        tasks_seen.add(it.task_id)
```

- [ ] **Step 5: Commit**

```bash
git add downloader/scheduler.py
git commit -m "feat: add _sync_task_stats to maintain parent task display stats"
```

---

### Task 3: backend/app.py 注册 Scheduler 回调

**Files:**
- Modify: `backend/app.py`

**Interfaces:**
- Consumes: `Scheduler` on_item_completed / on_item_failed / on_progress 回调签名

- [ ] **Step 1: 实现回调函数并注册**

在 `backend/app.py` 中，将原有：

```python
ctx.scheduler = Scheduler(
    conn=ctx.conn,
    http_client=None,
    on_item_completed=None,
    on_item_failed=None,
    on_progress=None,
    video_parser=ctx.video_parser,
    cookie_repository=ctx.cookie_repo,
)
```

替换为：

```python
def _on_item_completed(task_item_id: int) -> None:
    """下载完成回调：记录日志并触发 WebSocket 广播。"""
    log.info("任务项 %d 下载完成", task_item_id)
    # 通过 WebSocket manager 广播完成事件
    asyncio.create_task(
        ws_router.manager.broadcast({
            "type": "item_completed",
            "task_item_id": task_item_id,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
    )


def _on_item_failed(task_item_id: int, fail_reason: str) -> None:
    """下载失败回调：记录日志并触发 WebSocket 广播。"""
    log.warning("任务项 %d 下载失败: %s", task_item_id, fail_reason)
    asyncio.create_task(
        ws_router.manager.broadcast({
            "type": "item_failed",
            "task_item_id": task_item_id,
            "fail_reason": fail_reason,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
    )


def _on_progress(updates: list) -> None:
    """进度回调：通过 WebSocket 广播进度更新。"""
    if not updates:
        return
    asyncio.create_task(
        ws_router.manager.broadcast({
            "type": "progress",
            "updates": [
                {
                    "task_item_id": u.task_item_id,
                    "downloaded_bytes": u.downloaded_bytes,
                    "total_bytes": u.total_bytes,
                    "progress": round(u.progress, 1),
                    "status": u.status,
                }
                for u in updates
            ],
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
    )


ctx.scheduler = Scheduler(
    conn=ctx.conn,
    http_client=None,
    on_item_completed=_on_item_completed,
    on_item_failed=_on_item_failed,
    on_progress=_on_progress,
    video_parser=ctx.video_parser,
    cookie_repository=ctx.cookie_repo,
)
```

- [ ] **Step 2: 验证导入正确性并运行**

```bash
cd D:/Program/Douyin_Catcher && python -c "import backend.app; print('import ok')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat: register scheduler callbacks with WebSocket broadcast"
```

---

### Task 4: REST API 完成状态归一化

**Files:**
- Modify: `backend/api/download.py`
- Message Reference: `backend/api/ws.py:105-142` `_push_progress_updates`

- [ ] **Step 1: 修改 API progress 计算，完成项强制 100**

在 `download.py` 的 `list_task_items` 中：

```python
# 替换 progress 计算逻辑
progress = (
    (item.downloaded_bytes / max(item.total_bytes, 1)) * 100
    if item.total_bytes > 0
    else 0.0
)
if item.status == "completed":
    progress = 100.0
```

- [ ] **Step 2: 修改 clear_completed 只删除已完成项**

`clear_completed` 当前按父任务状态删除，改为按 task_item 的实际完成状态：

```python
@router.post("/clear-completed")
async def clear_completed():
    """清除所有已完成的任务项及空父任务。"""
    if ctx.task_repo is None or ctx.task_item_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    completed_items = ctx.task_item_repo.get_by_status("completed")
    deleted_tasks: set[int] = set()
    
    for item in completed_items:
        if item.id is not None:
            ctx.task_item_repo.delete(item.id)
            deleted_tasks.add(item.task_id)
    
    # 清理没有剩余 task_items 的空父任务
    for task_id in deleted_tasks:
        remaining = ctx.task_item_repo.get_by_task(task_id)
        if not remaining:
            ctx.task_repo.delete(task_id)
    
    return {"message": f"已清除 {len(completed_items)} 个已完成任务项"}
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/download.py
git commit -m "fix: normalize completed progress to 100 and clear based on item status"
```

---

### Task 5: WebSocket 推送终态及完成进度归 100

**Files:**
- Modify: `backend/api/ws.py`

**Interfaces:**
- Consumes: `ctx.task_item_repo.get_by_status()` 读取 `downloading`、`completed`、`failed` 状态

- [ ] **Step 1: 修改 _push_progress_updates 推送更多状态**

当前 `_push_progress_updates` 只查询 `downloading`，改为查询所有可展示状态并推送：

```python
async def _push_progress_updates(ws: WebSocket, stop_event: asyncio.Event) -> None:
    """定期推送进度更新。
    
    每 1 秒推送一次 downloading/completed/failed 任务项进度。
    """
    while not stop_event.is_set():
        try:
            if ctx.task_item_repo is not None:
                all_updates: list[dict] = []
                
                for status in ("downloading", "completed", "failed"):
                    items = ctx.task_item_repo.get_by_status(status)
                    for item in items:
                        if item.id is None:
                            continue
                        
                        progress: float = 0.0
                        if status == "completed":
                            progress = 100.0
                        elif item.total_bytes > 0:
                            progress = (item.downloaded_bytes / item.total_bytes) * 100.0
                        
                        all_updates.append({
                            "task_item_id": item.id,
                            "downloaded_bytes": item.downloaded_bytes,
                            "total_bytes": item.total_bytes,
                            "progress": round(progress, 1),
                            "status": item.status,
                            "aweme_id": item.aweme_id,
                        })
                
                if all_updates:
                    await ws.send_json({
                        "type": "progress",
                        "updates": all_updates,
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                    })
        except Exception:
            pass
        await asyncio.sleep(1)
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/ws.py
git commit -m "fix: push completed/failed status via WebSocket with normalized progress"
```

---

### Task 6: 前端 Store 刷新竞态保护与完成状态归一化

**Files:**
- Modify: `frontend/src/store/taskStore.ts`

- [ ] **Step 1: 修改 applyProgressUpdate，完成状态强制 100%**

```typescript
// taskStore.ts applyProgressUpdate

applyProgressUpdate: (update) => {
    set((state) => ({
      items: state.items.map((item) =>
        item.id === update.task_item_id
          ? {
              ...item,
              progress: update.status === "completed" ? 100 : update.progress,
              status: update.status as api.TaskStatus,
              downloadedBytes: update.downloaded_bytes,
              totalBytes: update.total_bytes,
            }
          : item,
      ),
    }));
  },
```

- [ ] **Step 2: 修改 loadTasks，合并时保留已有终态和更高进度**

```typescript
// taskStore.ts loadTasks

loadTasks: async () => {
    set({ loading: true, error: null });
    try {
      const tasks = await api.fetchTasks();
      const freshItems: DisplayTask[] = [];
      for (const task of tasks) {
        try {
          const items = await api.fetchTaskItems(task.id);
          freshItems.push(...items.map(mapTaskItem));
        } catch {
          // 单个任务加载失败不阻断整体
        }
      }
      
      // 合并：已存在的 completed/failed 项保留，更高进度的项保留
      set((state) => {
        const existingMap = new Map(state.items.map((i) => [i.id, i]));
        const merged: DisplayTask[] = freshItems.map((fresh) => {
          const existing = existingMap.get(fresh.id);
          if (!existing) return fresh;
          
          // 如果已有项是终态（completed/failed），且新的不是或一样，保留已有
          const isTerminal = (s: api.TaskStatus) => s === "completed" || s === "failed";
          if (isTerminal(existing.status) && !isTerminal(fresh.status)) {
            return existing;
          }
          // 如果已有项进度更高，保留已有
          if (existing.progress > fresh.progress && existing.status === fresh.status) {
            return existing;
          }
          return fresh;
        });
        return { items: merged, tasks, loading: false };
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "加载任务失败", loading: false });
    }
  },
```

- [ ] **Step 3: TypeScript 类型检查**

```bash
cd D:/Program/Douyin_Catcher/frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/store/taskStore.ts
git commit -m "fix: protect terminal states on refresh and normalize completed progress"
```

---

### Task 7: 后端测试 — Scheduler 回调与统计同步

**Files:**
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 测试 _sync_task_stats 完成统计**

```python
class TestTaskStatsSync:
    """父任务统计同步测试。"""
    
    def test_sync_task_stats_all_completed(self, memory_db, task_repo):
        """所有任务项完成时，父任务 status=completed，completed_items=总数。"""
        from downloader.scheduler import Scheduler
        from app.repositories import TaskItemRepository
        
        task = Task(id=None, source_type="single", source_url="x", status="pending", download_dir="/tmp")
        tid = task_repo.create(task)
        item_repo = TaskItemRepository(memory_db)
        
        for i in range(3):
            item = TaskItem(id=None, task_id=tid, aweme_id=f"aw{i}", url=f"http://x/{i}", type="video", status="completed")
            item_repo.create(item)
        
        s = Scheduler(conn=memory_db)
        s._sync_task_stats(tid)
        
        t = task_repo.get(tid)
        assert t is not None
        assert t.completed_items == 3
        assert t.status == "completed"
    
    def test_sync_task_stats_mixed_active(self, memory_db, task_repo):
        """存在进行中项时，父任务 status=downloading。"""
        from downloader.scheduler import Scheduler
        from app.repositories import TaskItemRepository
        
        task = Task(id=None, source_type="single", source_url="x", status="pending", download_dir="/tmp")
        tid = task_repo.create(task)
        item_repo = TaskItemRepository(memory_db)
        
        item_repo.create(TaskItem(id=None, task_id=tid, aweme_id="a1", url="http://x/1", type="video", status="completed"))
        item_repo.create(TaskItem(id=None, task_id=tid, aweme_id="a2", url="http://x/2", type="video", status="downloading"))
        item_repo.create(TaskItem(id=None, task_id=tid, aweme_id="a3", url="http://x/3", type="video", status="failed"))
        
        s = Scheduler(conn=memory_db)
        s._sync_task_stats(tid)
        
        t = task_repo.get(tid)
        assert t.status == "downloading"
        assert t.completed_items == 1
    
    def test_sync_task_stats_all_failed(self, memory_db, task_repo):
        """全部失败且无活动项时，父任务 status=failed。"""
        from downloader.scheduler import Scheduler
        from app.repositories import TaskItemRepository
        
        task = Task(id=None, source_type="single", source_url="x", status="pending", download_dir="/tmp")
        tid = task_repo.create(task)
        item_repo = TaskItemRepository(memory_db)
        
        item_repo.create(TaskItem(id=None, task_id=tid, aweme_id="a1", url="http://x/1", type="video", status="failed"))
        
        s = Scheduler(conn=memory_db)
        s._sync_task_stats(tid)
        
        t = task_repo.get(tid)
        assert t.status == "failed"
    
    def test_sync_task_stats_does_not_change_items(self, memory_db, task_repo):
        """_sync_task_stats 不修改任何 task_item 的状态。"""
        from downloader.scheduler import Scheduler
        from app.repositories import TaskItemRepository
        
        task = Task(id=None, source_type="single", source_url="x", status="pending", download_dir="/tmp")
        tid = task_repo.create(task)
        item_repo = TaskItemRepository(memory_db)
        
        iid = item_repo.create(TaskItem(id=None, task_id=tid, aweme_id="a1", url="http://x/1", type="video", status="downloading"))
        
        s = Scheduler(conn=memory_db)
        s._sync_task_stats(tid)
        
        item = item_repo.get(iid)
        assert item.status == "downloading"  # 不改任务项
```

- [ ] **Step 2: 运行测试**

```bash
cd D:/Program/Douyin_Catcher && python -m pytest tests/test_scheduler.py -k "TaskStatsSync" -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_scheduler.py
git commit -m "test: add _sync_task_stats and parent task display stat tests"
```

---

### Task 8: 后端测试 — API 进度归一化与清空已完成

**Files:**
- Create: `tests/test_api_download.py`

- [ ] **Step 1: 创建测试文件**

```python
"""下载 API 端点测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import Task, TaskItem
from app.repositories import TaskItemRepository, TaskRepository


@pytest.fixture
def api_client(memory_db):
    """创建带内存数据库的 FastAPI TestClient。"""
    from backend.app import app
    from backend.state import ctx
    
    # 注入测试仓库
    ctx.conn = memory_db
    ctx.task_repo = TaskRepository(memory_db)
    ctx.task_item_repo = TaskItemRepository(memory_db)
    
    # 需要 scheduler，但测试不实际下载，使用 mock
    from unittest.mock import AsyncMock, MagicMock
    mock_scheduler = MagicMock()
    mock_scheduler.add_task_items = MagicMock()
    mock_scheduler.pause = AsyncMock()
    mock_scheduler.resume = AsyncMock()
    mock_scheduler.pause_all = AsyncMock()
    mock_scheduler.resume_all = AsyncMock()
    ctx.scheduler = mock_scheduler
    
    with TestClient(app) as client:
        yield client


class TestTaskItemProgress:
    """任务项进度 API 测试。"""

    def test_completed_item_returns_100_progress(self, api_client, memory_db):
        """完成任务项 API 返回 progress=100。"""
        task_repo = TaskRepository(memory_db)
        item_repo = TaskItemRepository(memory_db)

        tid = task_repo.create(Task(
            id=None, source_type="single", source_url="x",
            status="downloading", download_dir="/tmp",
        ))
        iid = item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="aw1", url="http://x/1",
            type="video", status="completed", total_bytes=0, downloaded_bytes=0,
        ))

        resp = api_client.get(f"/api/download/tasks/{tid}/items")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "completed"
        assert data[0]["progress"] == 100.0

    def test_downloading_item_progress_from_bytes(self, api_client, memory_db):
        """下载中任务项 progress 由字节数计算。"""
        task_repo = TaskRepository(memory_db)
        item_repo = TaskItemRepository(memory_db)

        tid = task_repo.create(Task(
            id=None, source_type="single", source_url="x",
            status="downloading", download_dir="/tmp",
        ))
        item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="aw1", url="http://x/1",
            type="video", status="downloading", total_bytes=200, downloaded_bytes=150,
        ))

        resp = api_client.get(f"/api/download/tasks/{tid}/items")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["progress"] == 75.0


class TestClearCompleted:
    """清空已完成 API 测试。"""

    def test_clear_only_removes_completed_items(self, api_client, memory_db):
        """清空只删除已完成项，保留进行中/失败项。"""
        task_repo = TaskRepository(memory_db)
        item_repo = TaskItemRepository(memory_db)

        tid = task_repo.create(Task(
            id=None, source_type="single", source_url="x",
            status="downloading", download_dir="/tmp",
        ))
        completed_id = item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="c1", url="http://x/c1",
            type="video", status="completed",
        ))
        downloading_id = item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="d1", url="http://x/d1",
            type="video", status="downloading",
        ))
        failed_id = item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="f1", url="http://x/f1",
            type="video", status="failed",
        ))

        resp = api_client.post("/api/download/clear-completed")
        assert resp.status_code == 200

        # 已完成项被删除
        assert item_repo.get(completed_id) is None
        # 进行中项和失败项仍存在
        assert item_repo.get(downloading_id) is not None
        assert item_repo.get(failed_id) is not None

    def test_clear_completed_does_not_block_other_items(self, api_client, memory_db):
        """清空完成后进行中项状态和进度不变。"""
        task_repo = TaskRepository(memory_db)
        item_repo = TaskItemRepository(memory_db)

        tid = task_repo.create(Task(
            id=None, source_type="single", source_url="x",
            status="downloading", download_dir="/tmp",
        ))
        downloading_id = item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="d1", url="http://x/d1",
            type="video", status="downloading", total_bytes=100, downloaded_bytes=97,
        ))
        item_repo.create(TaskItem(
            id=None, task_id=tid, aweme_id="c1", url="http://x/c1",
            type="video", status="completed",
        ))

        resp = api_client.post("/api/download/clear-completed")
        assert resp.status_code == 200

        # 进行中项状态和进度不变
        item = item_repo.get(downloading_id)
        assert item.status == "downloading"
        assert item.downloaded_bytes == 97
        assert item.total_bytes == 100
```

- [ ] **Step 2: 运行测试**

```bash
cd D:/Program/Douyin_Catcher && python -m pytest tests/test_api_download.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_download.py
git commit -m "test: add API progress normalization and clear-completed tests"
```

---

### Task 9: 后端测试 — WebSocket 终态推送

**Files:**
- Create: `tests/test_ws.py`

- [ ] **Step 1: 创建 WebSocket 测试**

```python
"""WebSocket 进度推送测试。"""

from __future__ import annotations

import asyncio

import pytest

from app.models import Task, TaskItem
from app.repositories import TaskItemRepository, TaskRepository


@pytest.mark.asyncio
async def test_ws_pushes_all_statuses(memory_db):
    """WebSocket 推送 downloading/completed/failed 三种状态的任务项。"""
    from backend.api.ws import _push_progress_updates
    from backend.state import ctx

    task_repo = TaskRepository(memory_db)
    item_repo = TaskItemRepository(memory_db)
    ctx.task_item_repo = item_repo

    tid = task_repo.create(Task(
        id=None, source_type="single", source_url="x",
        status="downloading", download_dir="/tmp",
    ))
    downloading_id = item_repo.create(TaskItem(
        id=None, task_id=tid, aweme_id="d1", url="http://x/d1",
        type="video", status="downloading", total_bytes=100, downloaded_bytes=50,
    ))
    completed_id = item_repo.create(TaskItem(
        id=None, task_id=tid, aweme_id="c1", url="http://x/c1",
        type="video", status="completed", total_bytes=200, downloaded_bytes=200,
    ))
    failed_id = item_repo.create(TaskItem(
        id=None, task_id=tid, aweme_id="f1", url="http://x/f1",
        type="video", status="failed", total_bytes=0, downloaded_bytes=0,
    ))

    received: list[dict] = []

    class FakeWS:
        async def send_json(self, data):
            received.append(data)

    stop_event = asyncio.Event()
    push_task = asyncio.create_task(_push_progress_updates(FakeWS(), stop_event))

    # 等待一次推送
    await asyncio.sleep(1.1)
    stop_event.set()
    await push_task

    progress_msgs = [m for m in received if m["type"] == "progress"]
    assert len(progress_msgs) >= 1

    updates = progress_msgs[0]["updates"]
    update_map = {u["task_item_id"]: u for u in updates}

    # 三种状态都出现在推送中
    assert downloading_id in update_map
    assert completed_id in update_map
    assert failed_id in update_map

    # 完成项进度强制为 100
    assert update_map[completed_id]["progress"] == 100.0
    assert update_map[completed_id]["status"] == "completed"

    # 下载中进度按字节计算
    assert update_map[downloading_id]["progress"] == 50.0

    # 失败项进度为 0
    assert update_map[failed_id]["status"] == "failed"
```

- [ ] **Step 2: 运行测试**

```bash
cd D:/Program/Douyin_Catcher && python -m pytest tests/test_ws.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_ws.py
git commit -m "test: add WebSocket terminal status push test"
```

---

### Task 10: 全量测试验证

- [ ] **Step 1: 运行所有后端测试**

```bash
cd D:/Program/Douyin_Catcher && python -m pytest tests/ -x -q
```

- [ ] **Step 2: 前端 TypeScript 类型检查**

```bash
cd D:/Program/Douyin_Catcher/frontend && npx tsc --noEmit
```

- [ ] **Step 3: 前端构建**

```bash
cd D:/Program/Douyin_Catcher/frontend && npm run build
```

- [ ] **Step 4: 检查 lint（可选）**

```bash
cd D:/Program/Douyin_Catcher && ruff check app/ backend/ downloader/
```

- [ ] **Step 5: 验证完成并提交如有修正**

```bash
git status
# 如有未提交变更：
git add -A
git commit -m "chore: final verification adjustments"
```
