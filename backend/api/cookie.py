"""Cookie REST API。

暴露 Cookie 的增删查改、测试等功能。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import Cookie
from backend.state import ctx

router = APIRouter()


# === 请求/响应模型 ===


class CookieResponse(BaseModel):
    """Cookie 响应。"""

    id: int | None
    content: str
    label: str | None
    status: str
    last_used: str | None
    last_check: str | None
    fail_count: int
    created_at: str


class AddCookieRequest(BaseModel):
    """添加 Cookie 请求。"""

    content: str
    label: str | None = None


class TestCookieResponse(BaseModel):
    """Cookie 测试结果。"""

    id: int
    is_valid: bool
    error_message: str = ""
    user_nickname: str | None = None


# === API 端点 ===


@router.get("/list", response_model=list[CookieResponse])
async def list_cookies():
    """获取所有 Cookie 列表。"""
    if ctx.cookie_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    cookies = ctx.cookie_repo.get_all()
    return [
        CookieResponse(
            id=c.id,
            content=c.content,
            label=c.label,
            status=c.status,
            last_used=c.last_used,
            last_check=c.last_check,
            fail_count=c.fail_count,
            created_at=c.created_at,
        )
        for c in cookies
    ]


@router.post("/add")
async def add_cookie(req: AddCookieRequest):
    """添加新 Cookie。"""
    if ctx.cookie_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    cookie = Cookie(
        id=None,
        content=req.content,
        label=req.label,
        status="untested",
    )
    cookie_id = ctx.cookie_repo.add(cookie)
    return {"id": cookie_id, "message": "Cookie 已添加"}


@router.post("/test/{cookie_id}", response_model=TestCookieResponse)
async def test_cookie(cookie_id: int):
    """测试单个 Cookie 的有效性。"""
    if ctx.cookie_repo is None or ctx.cookie_tester is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    cookie = ctx.cookie_repo.get_by_id(cookie_id)
    if cookie is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")

    # 调用测试器
    result = await ctx.cookie_tester.test_cookie(cookie.content)

    # 更新 Cookie 状态
    new_status = "valid" if result.is_valid else "invalid"
    ctx.cookie_repo.update_status(cookie_id, new_status)

    return TestCookieResponse(
        id=cookie_id,
        is_valid=result.is_valid,
        error_message=result.error_message,
        user_nickname=result.user_nickname,
    )


@router.post("/test-all", response_model=list[TestCookieResponse])
async def test_all_cookies():
    """测试所有未失效的 Cookie。"""
    if ctx.cookie_repo is None or ctx.cookie_tester is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    cookies = ctx.cookie_repo.test_all()
    results = []
    for cookie in cookies:
        if cookie.id is None:
            continue
        result = await ctx.cookie_tester.test_cookie(cookie.content)
        new_status = "valid" if result.is_valid else "invalid"
        ctx.cookie_repo.update_status(cookie.id, new_status)
        results.append(
            TestCookieResponse(
                id=cookie.id,
                is_valid=result.is_valid,
                error_message=result.error_message,
                user_nickname=result.user_nickname,
            )
        )
    return results


@router.delete("/{cookie_id}")
async def delete_cookie(cookie_id: int):
    """删除指定 Cookie。"""
    if ctx.cookie_repo is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    cookie = ctx.cookie_repo.get_by_id(cookie_id)
    if cookie is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    ctx.cookie_repo.remove(cookie_id)
    return {"message": f"Cookie {cookie_id} 已删除"}
