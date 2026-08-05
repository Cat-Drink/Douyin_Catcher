"""下载任务 REST API。

暴露任务列表、启动下载、暂停/恢复/重试、清除已完成等接口。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import Task, TaskItem, TaskItemStatus, TaskStatus
from backend.state import ctx

router = APIRouter()


# === 请求/响应模型 ===


class StartDownloadRequest(BaseModel):
    """启动下载请求。"""

    source_type: str = "single"
    source_url: str | None = None
    items: list[dict] | None = None  # 批量下载时传入解析后的 items
    download_dir: str | None = None


class TaskResponse(BaseModel):
    """任务列表响应项。"""

    id: int
    source_type: str
    source_url: str | None
    status: str
    total_items: int
    completed_items: int
    created_at: str
    updated_at: str
    download_dir: str


class TaskItemResponse(BaseModel):
    """任务项响应。"""

    id: int | None
    task_id: int
    aweme_id: str | None
    url: str
    title: str | None
    author: str | None
    type: str
    status: str
    downloaded_bytes: int
    total_bytes: int
    progress: float = 0.0
    cover_url: str | None = None
    fail_reason: str | None
    local_path: str | None


# === API 端点 ===


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks():
    """获取所有下载任务列表。"""
    if ctx.task_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    # 简单获取所有任务 - 通过遍历 id 方式
    # 更高效的方式是加一个 get_all 方法
    tasks = []
    # 尝试从 1 到 1000 扫描，找到所有任务
    for tid in range(1, 1001):
        task = ctx.task_repo.get(tid)
        if task is None:
            continue
        tasks.append(
            TaskResponse(
                id=task.id,
                source_type=task.source_type,
                source_url=task.source_url,
                status=task.status,
                total_items=task.total_items,
                completed_items=task.completed_items,
                created_at=task.created_at,
                updated_at=task.updated_at,
                download_dir=task.download_dir,
            )
        )
    return tasks


@router.get("/tasks/{task_id}/items", response_model=list[TaskItemResponse])
async def list_task_items(task_id: int):
    """获取指定任务的下载项列表。"""
    if ctx.task_item_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    items = ctx.task_item_repo.get_by_task(task_id)
    return [
        TaskItemResponse(
            id=item.id,
            task_id=item.task_id,
            aweme_id=item.aweme_id,
            url=item.url,
            title=item.title,
            author=item.author,
            type=item.type,
            status=item.status,
            downloaded_bytes=item.downloaded_bytes,
            total_bytes=item.total_bytes,
            progress=(
                (item.downloaded_bytes / max(item.total_bytes, 1)) * 100
                if item.total_bytes > 0
                else 0.0
            ),
            cover_url=item.cover_url,
            fail_reason=item.fail_reason,
            local_path=item.local_path,
        )
        for item in items
    ]


@router.post("/start")
async def start_download(req: StartDownloadRequest):
    """启动下载任务。"""
    if ctx.task_repo is None or ctx.task_item_repo is None or ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    download_dir = req.download_dir or ctx.config_repo.get("download_dir") or ""

    # 创建任务
    task = Task(
        id=None,
        source_type=req.source_type,
        source_url=req.source_url,
        status=TaskStatus.PENDING.value,
        download_dir=download_dir,
    )
    task_id = ctx.task_repo.create(task)

    # 如果有传入 items，直接创建 task_items 并入队
    if req.items:
        items = []
        # 获取有效 Cookie（供二次解析真实媒体地址）
        cookie = ""
        if ctx.cookie_repo is not None:
            valid_cookie = ctx.cookie_repo.get_valid()
            if valid_cookie is not None:
                cookie = valid_cookie.content

        for item_data in req.items:
            item_type = item_data.get("type", "video")
            aweme_id = item_data.get("aweme_id")
            media_url = item_data.get("no_watermark_url") or ""
            image_urls = item_data.get("image_urls") or []

            # 前端未提供真实媒体地址时，用 aweme_id 二次解析 detail 接口获取
            if not (media_url or image_urls) and aweme_id and ctx.video_parser is not None:
                try:
                    video_info = await ctx.video_parser.parse_video(aweme_id, cookie)
                    if item_type == "image_set" and video_info.image_urls:
                        image_urls = video_info.image_urls
                    elif video_info.no_watermark_url:
                        media_url = video_info.no_watermark_url
                except Exception:
                    # 解析失败时回退到原始 URL，交由下载器/用户界面反馈
                    pass

            # 图集：换行分隔多张图片 URL；视频：使用无水印直链
            if item_type == "image_set" and image_urls:
                download_url = "\n".join(image_urls)
            elif media_url:
                download_url = media_url
            else:
                download_url = item_data.get("url", "")

            task_item = TaskItem(
                id=None,
                task_id=task_id,
                aweme_id=aweme_id,
                url=download_url,
                title=item_data.get("title"),
                author=item_data.get("author"),
                type=item_type,
                cover_url=item_data.get("cover_url"),
                image_count=(
                    len(image_urls)
                    if item_type == "image_set" and image_urls
                    else item_data.get("image_count")
                ),
                status=TaskItemStatus.PENDING.value,
            )
            item_id = ctx.task_item_repo.create(task_item)
            task_item.id = item_id
            items.append(task_item)

        # 更新任务总数
        ctx.task_repo.update_progress(task_id, 0, len(items))

        # 入队调度
        ctx.scheduler.add_task_items(items)

    return {"task_id": task_id, "message": "下载任务已创建"}


@router.post("/pause/{task_item_id}")
async def pause_download(task_item_id: int):
    """暂停指定下载项。"""
    if ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    await ctx.scheduler.pause(task_item_id)
    return {"message": f"task_item {task_item_id} 已暂停"}


@router.post("/resume/{task_item_id}")
async def resume_download(task_item_id: int):
    """恢复指定下载项。"""
    if ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    await ctx.scheduler.resume(task_item_id)
    return {"message": f"task_item {task_item_id} 已恢复"}


@router.post("/retry/{task_item_id}")
async def retry_download(task_item_id: int):
    """重新执行下载项：重置为待下载状态并重新入队。"""
    if ctx.task_item_repo is None or ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    item = ctx.task_item_repo.get(task_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="任务项不存在")
    ctx.task_item_repo.reset_for_retry(task_item_id)
    # 状态已重置为 pending，不会被已完成去重跳过
    ctx.scheduler.add_task_items([item])
    return {"message": f"任务项 {task_item_id} 已重新入队"}


@router.post("/pause-all")
async def pause_all():
    """暂停所有下载。"""
    if ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    await ctx.scheduler.pause_all()
    return {"message": "所有下载已暂停"}


@router.post("/resume-all")
async def resume_all():
    """恢复所有暂停的下载。"""
    if ctx.scheduler is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    await ctx.scheduler.resume_all()
    return {"message": "所有暂停任务已恢复"}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    """删除任务及其所有项。"""
    if ctx.task_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    ctx.task_repo.delete(task_id)
    return {"message": f"任务 {task_id} 已删除"}


@router.post("/clear-completed")
async def clear_completed():
    """清除所有已完成的任务。"""
    if ctx.task_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    # 获取所有已完成任务
    completed = ctx.task_repo.get_by_status(TaskStatus.COMPLETED.value)
    for task in completed:
        if task.id is not None:
            ctx.task_repo.delete(task.id)
    return {"message": f"已清除 {len(completed)} 个已完成任务"}
