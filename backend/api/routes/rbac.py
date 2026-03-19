# -*- coding: utf-8 -*-
"""
RBAC API：

- /rbac/roles：角色管理（admin）
- /rbac/menus：菜单管理（admin）
- /rbac/users/{user_id}/roles：用户关联角色（admin）
- /rbac/roles/{role_code}/menus：角色关联菜单（admin）
- /rbac/menus/me：当前用户菜单（用于后台侧边栏渲染）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for

router = APIRouter(prefix="/rbac", tags=["rbac"])


def _is_admin(role: str | None) -> bool:
    r = (role or "").strip().lower()
    return r in ("admin", "administrator", "ops_admin")


def _forbidden():
    return JSONResponse(
        status_code=200,
        content=envelope(code=ErrorCode.FORBIDDEN, message=message_for(ErrorCode.FORBIDDEN), data=None),
    )


class RoleUpsertBody(BaseModel):
    code: str = Field(default="", description="角色 code，如 admin、auditor")
    name: str = Field(default="", description="角色名称")
    description: str = ""
    enabled: bool = True


class MenuUpsertBody(BaseModel):
    code: str = Field(default="", description="菜单 code")
    name: str = Field(default="", description="菜单名称")
    path: str = Field(default="", description="路由路径")
    icon: str = Field(default="", description="图标名（与前端 icon 映射一致）")
    parent_id: int | None = Field(default=None, description="父菜单ID（可选）")
    sort_order: int = 0
    enabled: bool = True


class SetUserRolesBody(BaseModel):
    role_codes: list[str] = Field(default_factory=list)


class SetRoleMenusBody(BaseModel):
    menu_codes: list[str] = Field(default_factory=list)


@router.get("/roles")
async def list_roles(auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from rbac.store import list_roles as _list

        items = _list()
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.post("/roles")
async def upsert_role(body: RoleUpsertBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    payload = body.model_dump()
    try:
        from rbac.store import upsert_role as _upsert

        ok = _upsert(payload)
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.get("/menus")
async def list_menus(auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from rbac.store import list_menus as _list

        items = _list()
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.post("/menus")
async def upsert_menu(body: MenuUpsertBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    payload = body.model_dump()
    try:
        from rbac.store import upsert_menu as _upsert

        ok = _upsert(payload)
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.put("/users/{user_id}/roles")
async def set_user_roles(user_id: str, body: SetUserRolesBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from rbac.store import set_user_roles as _set

        ok = _set(user_id, body.role_codes)
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.get("/users/{user_id}/roles")
async def get_user_roles(user_id: str, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from rbac.store import get_user_roles as _get

        items = _get(user_id)
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.put("/roles/{role_code}/menus")
async def set_role_menus(role_code: str, body: SetRoleMenusBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from rbac.store import set_role_menus as _set

        ok = _set(role_code, body.menu_codes)
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.get("/roles/{role_code}/menus")
async def get_role_menus(role_code: str, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from rbac.store import get_role_menus as _get

        items = _get(role_code)
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )


@router.get("/menus/me")
async def my_menus(auth=Depends(get_auth_context)):
    """
    返回当前用户拥有的后台菜单（树形结构）。
    普通用户默认无角色 → 返回空数组（前端将展示空侧栏/或仅固定项）。
    """
    try:
        from rbac.store import list_user_menus as _list

        items = _list(getattr(auth, "user_id", "") or "")
        # build tree
        by_parent: dict[int | None, list[dict]] = {}
        for it in items:
            by_parent.setdefault(it.get("parent_id"), []).append(it)

        def build(parent_id: int | None) -> list[dict]:
            nodes = by_parent.get(parent_id, [])
            out = []
            for n in nodes:
                obj = {"code": n["code"], "name": n["name"], "path": n.get("path") or "", "icon": n.get("icon") or ""}
                children = build(None if n.get("id") is None else int(n.get("id")))  # parent_id uses numeric id
                if children:
                    obj["children"] = children
                out.append(obj)
            return out

        # 由于本实现的菜单 parent_id 以 menus.id 作为父子关系，而 my_menus 查询结果未带 id，
        # 所以暂不做树形（默认后台菜单为扁平）。后续菜单管理页面完善 parent_id 后可扩展查询字段。
        flat = [{"code": x["code"], "name": x["name"], "path": x.get("path") or "", "icon": x.get("icon") or ""} for x in items]
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": flat}))
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )

