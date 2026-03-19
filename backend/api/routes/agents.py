# -*- coding: utf-8 -*-
"""
Agent 管理 API（MVP）：

- 展示内置/自定义 agent 配置
- 可编辑提示词(system_prompt)与模型选择(model_id)
- 可创建/删除 agent（custom）

权限：仅 admin 可写；读接口也默认限制为 admin（避免泄露内部提示词）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for


router = APIRouter(prefix="/agents", tags=["agents"])


def _is_admin(role: str | None) -> bool:
    r = (role or "").strip().lower()
    return r in ("admin", "administrator", "ops_admin")


def _forbidden():
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.FORBIDDEN, message=message_for(ErrorCode.FORBIDDEN), data=None))


class AgentUpsertBody(BaseModel):
    agent_key: str = Field(default="", description="唯一 key，如 product_query / custom_xxx")
    name: str = Field(default="", description="展示名")
    type: str = Field(default="custom", description="builtin | custom")
    enabled: bool = True
    system_prompt: str = Field(default="", description="system prompt")
    model_id: int | None = Field(default=None, description="模型配置ID（ai_models.id）")
    skill_keys: list[str] = Field(default_factory=list, description="该 agent 使用的 skill key 列表（按顺序尝试）")


@router.get("")
async def list_agents(includeDeleted: bool = False, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from agents.agent_store import list_agents as _list

        items = _list(include_deleted=bool(includeDeleted))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"items": items}))
    except Exception:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None))


@router.get("/{agent_key}")
async def get_agent(agent_key: str, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from agents.agent_store import get_agent as _get

        obj = _get(agent_key)
        if not obj or obj.get("deleted_at"):
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.NOT_FOUND, message="agent 不存在", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=obj))
    except Exception:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None))


@router.post("")
async def create_agent(body: AgentUpsertBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    payload = body.model_dump()
    payload["type"] = "custom"
    try:
        from agents.agent_store import get_agent as _get, upsert_agent as _upsert

        agent_key = (payload.get("agent_key") or "").strip()
        if not agent_key:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.VALIDATION_ERROR, message="agent_key 不能为空", data=None))
        # 防止覆盖内置 key（MVP：内置 key 只能走 PUT 更新）
        exist = _get(agent_key)
        if exist and not exist.get("deleted_at"):
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="agent_key 已存在", data=None))
        ok = _upsert(payload, actor_user_id=getattr(auth, "user_id", "") or "")
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="创建失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None))


@router.put("/{agent_key}")
async def update_agent(agent_key: str, body: AgentUpsertBody, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    payload = body.model_dump()
    payload["agent_key"] = (agent_key or "").strip()
    try:
        from agents.agent_store import upsert_agent as _upsert

        ok = _upsert(payload, actor_user_id=getattr(auth, "user_id", "") or "")
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="保存失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None))


@router.delete("/{agent_key}")
async def delete_agent(agent_key: str, auth=Depends(get_auth_context)):
    if not _is_admin(getattr(auth, "role", None)):
        return _forbidden()
    try:
        from agents.agent_store import get_agent as _get, soft_delete_agent as _del

        obj = _get(agent_key)
        if not obj or obj.get("deleted_at"):
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.NOT_FOUND, message="agent 不存在", data=None))
        if (obj.get("type") or "") == "builtin":
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.FORBIDDEN, message="内置 agent 不允许删除", data=None))
        ok = _del(agent_key, actor_user_id=getattr(auth, "user_id", "") or "")
        if not ok:
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.BAD_REQUEST, message="删除失败", data=None))
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))
    except Exception:
        return JSONResponse(status_code=200, content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None))

