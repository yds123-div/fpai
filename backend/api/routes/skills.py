# -*- coding: utf-8 -*-
"""
Skill 管理 API（MVP）：

- 展示 builtin/custom skills
- 导入（注册 module_path）/编辑/删除（软删）

权限：仅 admin 可读写（避免泄露内部模块信息）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for

router = APIRouter(prefix="/skills", tags=["skills"])


def _is_admin(role: str | None) -> bool:
    r = (role or "").strip().lower()
    return r in ("admin", "administrator", "ops_admin")


def _forbidden():
    return JSONResponse(
        status_code=200, content=envelope(code=ErrorCode.FORBIDDEN, message=message_for(ErrorCode.FORBIDDEN), data=None)
    )


class SkillUpsertBody(BaseModel):
    skill_key: str = Field(default="", description="唯一 key，如 product_compare / custom_xxx")
    name: str = Field(default="", description="展示名")
    type: str = Field(default="custom", description="builtin | custom")
    enabled: bool = True
    module_path: str = Field(default="", description="Python module path，需包含 run(question, ctx)")
    description: str = ""


@router.get("")
async def list_skills(includeDeleted: bool = False, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from agents.skills_store import list_skills as _list

        items = _list(include_deleted=bool(includeDeleted))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(
            status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None)
        )


@router.get("/{skill_key}")
async def get_skill(skill_key: str, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from agents.skills_store import get_skill as _get

        obj = _get(skill_key)
        if not obj or obj.get("deleted_at"):
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.NOT_FOUND, message="skill 不存在", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=obj))
    except Exception:
        return JSONResponse(
            status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None)
        )


@router.post("")
async def create_skill(body: SkillUpsertBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    payload = body.model_dump()
    payload["type"] = "custom"
    try:
        from agents.skills_store import get_skill as _get, upsert_skill as _upsert

        key = (payload.get("skill_key") or "").strip()
        if not key:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.VALIDATION_ERROR, message="skill_key 不能为空", data=None))
        exist = _get(key)
        if exist and not exist.get("deleted_at"):
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="skill_key 已存在", data=None))
        ok = _upsert(payload, actor_user_id=getattr(auth, "user_id", "") or "")
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="导入/创建失败（请检查 module_path 是否可用）", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None)
        )


@router.put("/{skill_key}")
async def update_skill(skill_key: str, body: SkillUpsertBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    payload = body.model_dump()
    payload["skill_key"] = (skill_key or "").strip()
    try:
        from agents.skills_store import upsert_skill as _upsert

        ok = _upsert(payload, actor_user_id=getattr(auth, "user_id", "") or "")
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败（请检查 module_path 是否可用）", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None)
        )


@router.delete("/{skill_key}")
async def delete_skill(skill_key: str, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from agents.skills_store import soft_delete_skill as _del

        ok = _del(skill_key, actor_user_id=getattr(auth, "user_id", "") or "")
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="删除失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(
            status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None)
        )

