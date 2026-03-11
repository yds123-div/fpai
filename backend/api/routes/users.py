# -*- coding: utf-8 -*-
"""
用户管理：分页查询、新增、修改、删除、重置密码。
需鉴权；前缀 /api/v1，路由 /users。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from pkg.codes import ErrorCode, envelope
from pkg.logger import get_logger

from api.deps import get_current_user_id
from auth.service import (
    list_users_paginated,
    create_user,
    update_user,
    delete_user,
    reset_user_password,
    get_user_by_id,
)

router = APIRouter(prefix="/users", tags=["users"])
logger = get_logger(__name__)


def _user_to_response(user: dict) -> dict:
    """与 auth 路由一致的 user 响应格式。"""
    return {
        "id": user.get("id", ""),
        "account": user.get("account", ""),
        "name": user.get("name", ""),
        "employee_no": user.get("employee_no", ""),
        "email": user.get("email", ""),
    }


# ---------- 请求体 ----------


class UserCreateBody(BaseModel):
    account: str = Field(..., min_length=1, description="登录账号")
    password: str = Field(..., min_length=1, description="明文密码（将经 bcrypt(SHA256) 存储）")
    name: str = ""
    employee_no: str = ""
    email: str = ""

    class Config:
        populate_by_name = True


class UserUpdateBody(BaseModel):
    name: str | None = None
    employee_no: str | None = None
    email: str | None = None

    class Config:
        populate_by_name = True


class ResetPasswordBody(BaseModel):
    newPassword: str = Field(..., min_length=1)

    class Config:
        populate_by_name = True


# ---------- 接口 ----------


@router.get("")
async def users_list(
    page: int = 1,
    page_size: int = 10,
    account: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """分页查询用户列表；支持按 account 模糊搜索。"""
    if not user_id:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="未登录", data=None)
    items, total = list_users_paginated(page=page, page_size=page_size, account_like=account)
    return envelope(
        code=ErrorCode.OK,
        message="ok",
        data={
            "items": [_user_to_response(u) for u in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/{user_id}")
async def users_get(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """根据 id 查询单个用户（不含密码）。"""
    if not current_user_id:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="未登录", data=None)
    user = get_user_by_id(user_id)
    if not user:
        return envelope(code=ErrorCode.NOT_FOUND, message="用户不存在", data=None)
    return envelope(code=ErrorCode.OK, message="ok", data=_user_to_response(user))


@router.post("")
async def users_create(
    body: UserCreateBody,
    current_user_id: str = Depends(get_current_user_id),
):
    """新增用户；account、name、email、employee_no 均须唯一（非空时校验）。"""
    if not current_user_id:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="未登录", data=None)
    user, conflict = create_user(
        account=body.account.strip(),
        password=body.password,
        name=body.name or "",
        employee_no=body.employee_no or "",
        email=body.email or "",
    )
    if conflict:
        _msg = {"account": "账号", "name": "姓名", "email": "邮箱", "employee_no": "工号"}
        return envelope(code=ErrorCode.BAD_REQUEST, message=f"{_msg.get(conflict, conflict)}已存在", data=None)
    if not user:
        return envelope(code=ErrorCode.BAD_REQUEST, message="参数无效", data=None)
    return envelope(code=ErrorCode.OK, message="ok", data=_user_to_response(user))


@router.put("/{user_id}")
async def users_update(
    user_id: str,
    body: UserUpdateBody,
    current_user_id: str = Depends(get_current_user_id),
):
    """更新用户信息（name、employee_no、email）；不修改账号与密码。name、email、employee_no 须唯一（非空时）。"""
    if not current_user_id:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="未登录", data=None)
    user, conflict = update_user(
        user_id=user_id,
        name=body.name,
        employee_no=body.employee_no,
        email=body.email,
    )
    if conflict:
        _msg = {"account": "账号", "name": "姓名", "email": "邮箱", "employee_no": "工号"}
        return envelope(code=ErrorCode.BAD_REQUEST, message=f"{_msg.get(conflict, conflict)}已存在", data=None)
    if not user:
        return envelope(code=ErrorCode.NOT_FOUND, message="用户不存在或未变更", data=None)
    return envelope(code=ErrorCode.OK, message="ok", data=_user_to_response(user))


@router.delete("/{user_id}")
async def users_delete(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """删除用户。"""
    if not current_user_id:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="未登录", data=None)
    ok = delete_user(user_id)
    if not ok:
        return envelope(code=ErrorCode.NOT_FOUND, message="用户不存在", data=None)
    return envelope(code=ErrorCode.OK, message="ok", data=None)


@router.post("/{user_id}/reset-password")
async def users_reset_password(
    user_id: str,
    body: ResetPasswordBody,
    current_user_id: str = Depends(get_current_user_id),
):
    """重置用户密码（明文传入，后端 bcrypt(SHA256) 后更新）。"""
    if not current_user_id:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="未登录", data=None)
    new_password = body.newPassword or ""
    if not new_password:
        return envelope(code=ErrorCode.VALIDATION_ERROR, message="新密码不能为空", data=None)
    ok = reset_user_password(user_id, new_password)
    if not ok:
        return envelope(code=ErrorCode.NOT_FOUND, message="用户不存在或重置失败", data=None)
    return envelope(code=ErrorCode.OK, message="ok", data=None)
