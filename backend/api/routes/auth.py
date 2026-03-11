# -*- coding: utf-8 -*-
"""
认证路由：POST /api/v1/auth/login、POST /api/v1/auth/logout、POST /api/v1/auth/change-password、GET /api/v1/auth/me、PUT /api/v1/auth/me（T027a）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import get_logger

from api.deps import get_current_user_id
from auth.service import (
    verify_user,
    issue_token,
    get_user_by_id,
    update_user,
    get_password_hash_by_user_id,
    verify_password,
    hash_password_from_digest,
    update_user_password_hash,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def _user_to_response(user: dict) -> dict:
    """将用户 dict 转为响应体 user 对象（id、account、name、employee_no、email）。"""
    return {
        "id": user.get("id", ""),
        "account": user.get("account", ""),
        "name": user.get("name", ""),
        "employee_no": user.get("employee_no", ""),
        "email": user.get("email", ""),
    }


from pydantic import BaseModel


class LoginBody(BaseModel):
    username: str = ""  # 前端以 username 提交
    password: str = ""  # 前端已用 SHA256 加密后传入，后端存储为 bcrypt(SHA256(明文))，直接比对


class ChangePasswordBody(BaseModel):
    old_password: str = ""
    new_password: str = ""  # 与登录约定一致：前端传 SHA256(新密码).hex


class UpdateMeBody(BaseModel):
    """当前用户修改自己的资料；id 仅用于前端回传，服务端以 Token 中的 user_id 为准。"""
    id: str = ""
    account: str = ""
    email: str = ""
    employee_no: str = ""
    name: str = ""


@router.post("/login")
async def auth_login(body: LoginBody):
    """
    账号+密码登录；成功返回 token 与 user（id、account、name、employee_no、email）。
    请求体：{ "username": "...", "password": "..." }；
    前端对密码做 SHA256 后传 password，后端与存储的 bcrypt(SHA256(明文)) 比对。
    说明：用户表中 password_hash 须为 bcrypt(SHA256(明文))；若此前存的是 bcrypt(明文)，需重置密码或重新执行种子/导入。
    """
    account = body.username or ""
    password = body.password or ""
    if not account:
        return envelope(code=ErrorCode.VALIDATION_ERROR, message="账号不能为空", data=None)
    user = verify_user(account, password)
    if not user:
        logger.info("auth_login: account=%s result=fail", account)
        return envelope(code=ErrorCode.UNAUTHORIZED, message="账号或密码错误", data=None)
    token = issue_token(user["id"])
    if not token:
        logger.info("auth_login: account=%s token=none result=fail", account)
        return envelope(code=ErrorCode.INTERNAL_ERROR, message="Token 签发失败", data=None)
    logger.info("auth_login: account=%s result=ok", account)
    return envelope(
        code=ErrorCode.OK,
        message="ok",
        data={"token": token, "user": _user_to_response(user)},
    )


@router.post("/logout")
async def auth_logout(user_id: str = Depends(get_current_user_id)):
    """
    用户退出登录。需携带有效 Bearer Token；服务端返回成功，客户端清除本地 token 与用户状态。
    JWT 无状态，服务端不保存会话，仅做鉴权并记录日志。
    """
    logger.info("auth_logout: user_id=%s", user_id)
    return envelope(code=ErrorCode.OK, message="ok", data=None)


@router.post("/change-password")
async def auth_change_password(
    body: ChangePasswordBody,
    user_id: str = Depends(get_current_user_id),
):
    """
    当前登录用户修改自己的密码。
    请求体：{ "old_password": "...", "new_password": "..." }。
    与登录约定一致：old_password、new_password 均为前端 SHA256(明文).hex。
    """
    old_password = (body.old_password or "").strip()
    new_password = (body.new_password or "").strip()
    if not old_password:
        return envelope(code=ErrorCode.VALIDATION_ERROR, message="请输入原密码", data=None)
    if not new_password:
        return envelope(code=ErrorCode.VALIDATION_ERROR, message="请输入新密码", data=None)
    stored_hash = get_password_hash_by_user_id(user_id)
    if not stored_hash:
        return envelope(code=ErrorCode.INTERNAL_ERROR, message="用户不存在或未设置密码", data=None)
    if not verify_password(old_password, stored_hash):
        logger.info("auth_change_password: user_id=%s old_password mismatch", user_id)
        return envelope(code=ErrorCode.INTERNAL_ERROR, message="原密码错误", data=None)
    new_hash = hash_password_from_digest(new_password)
    if not new_hash:
        return envelope(code=ErrorCode.INTERNAL_ERROR, message="密码加密失败", data=None)
    if not update_user_password_hash(user_id, new_hash):
        return envelope(code=ErrorCode.INTERNAL_ERROR, message="密码更新失败", data=None)
    logger.info("auth_change_password: user_id=%s success", user_id)
    return envelope(code=ErrorCode.OK, message="ok", data=None)


@router.get("/me")
async def auth_me(user_id: str = Depends(get_current_user_id)):
    """当前登录用户信息；鉴权中间件已校验 Bearer Token 并注入 user_id。"""
    user = get_user_by_id(user_id)
    if not user:
        return envelope(code=ErrorCode.UNAUTHORIZED, message="用户不存在", data=None)
    return envelope(code=ErrorCode.OK, message="ok", data={"user": _user_to_response(user)})


@router.put("/me")
async def auth_update_me(
    body: UpdateMeBody,
    user_id: str = Depends(get_current_user_id),
):
    """
    当前登录用户修改自己的资料。
    请求体：{ "id", "account", "email", "employee_no", "name" }；以 Token 中的 user_id 为准，仅更新 account、email、employee_no、name。
    """
    user, conflict = update_user(
        user_id,
        account=(body.account or "").strip() or None,
        name=(body.name or "").strip() or None,
        employee_no=(body.employee_no or "").strip() or None,
        email=(body.email or "").strip() or None,
    )
    if conflict:
        _msg = {"account": "账号", "name": "姓名", "email": "邮箱", "employee_no": "工号"}
        return envelope(code=ErrorCode.BAD_REQUEST, message=f"{_msg.get(conflict, conflict)}已存在", data=None)
    if not user:
        return envelope(code=ErrorCode.INTERNAL_ERROR, message="更新失败", data=None)
    logger.info("auth_update_me: user_id=%s success", user_id)
    return envelope(code=ErrorCode.OK, message="ok", data={"user": _user_to_response(user)})
