# -*- coding: utf-8 -*-
"""
Chat 路由：POST /api/v1/chat（T029）。

- 支持非流式（统一 envelope）与流式（SSE）。
- 会话：无 sessionId 时隐式创建；写回 productIds/customerProfile 到会话上下文（Redis，若可用）。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, is_dataclass
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import get_logger
from orchestrator.run import run_chat_turn_async
from orchestrator.session import (
    create_session,
    get_session,
    get_session_context_for_orchestration,
    update_session_context,
    append_message,
)

router = APIRouter(prefix="", tags=["chat"])
logger = get_logger(__name__)


class ChatBody(BaseModel):
    sessionId: str | None = Field(default=None)
    message: str = Field(default="")
    productIds: list[str] | None = Field(default=None)
    customerProfile: dict[str, Any] | str | None = Field(default=None)
    stream: bool | None = Field(default=True)


def _jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        return obj.dict()
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        return obj.to_dict()
    return obj


def _sse_event(event: str, data: Any) -> str:
    payload = json.dumps(_jsonable(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _stringify_customer_profile(profile: dict[str, Any] | str | None) -> str | None:
    if profile is None:
        return None
    if isinstance(profile, str):
        return profile.strip()
    try:
        return json.dumps(profile, ensure_ascii=False)
    except Exception:
        return str(profile)


def _chunk_text(text: str, chunk_size: int = 300) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= chunk_size:
        return [text]
    out: list[str] = []
    i = 0
    while i < len(text):
        out.append(text[i : i + chunk_size])
        i += chunk_size
    return out


@router.post("/chat")
async def chat(body: ChatBody, request: Request, auth=Depends(get_auth_context)):
    """
    多轮对话入口：支持 stream（SSE）与非流式。
    - stream=true：返回 text/event-stream，事件 message/citation/done/error。
    - stream=false：返回 JSON envelope，data 含 answerId、answerBlocks、citations、compliance、trace、suggestedQuestions。
    """
    # 1) 会话
    user_id = getattr(auth, "user_id", "") or ""
    session_id = (body.sessionId or "").strip() or None
    if session_id:
        if not get_session(session_id):
            return JSONResponse(
                status_code=200,
                content=envelope(code=ErrorCode.SESSION_NOT_FOUND, message=message_for(ErrorCode.SESSION_NOT_FOUND), data=None),
            )
    else:
        session_id = create_session(user_id=user_id)

    # 2) 更新会话上下文（写回）
    customer_profile_str = _stringify_customer_profile(body.customerProfile)
    update_session_context(
        session_id,
        product_ids=body.productIds if body.productIds is not None else None,
        customer_profile=customer_profile_str if body.customerProfile is not None else None,
    )

    # 3) 供编排使用的会话上下文（合并 request + session）
    ctx = get_session_context_for_orchestration(session_id)
    product_ids = body.productIds if body.productIds is not None else ctx.get("product_ids")
    customer_profile = customer_profile_str if body.customerProfile is not None else ctx.get("customer_profile")

    # 4) 权限上下文（传给编排/智能体/检索）
    permission_context = {
        "role": getattr(auth, "role", None),
        "productPoolIds": getattr(auth, "product_pool_ids", None) or [],
    }

    # 5) traceId（来自 X-Request-Id 中间件回传同值）
    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None

    # 6) 落用户消息（摘要）
    msg = (body.message or "").strip()
    append_message(session_id, "user", msg[:2000])

    async def _run_once() -> dict[str, Any]:
        result = await run_chat_turn_async(
            msg,
            session_id=session_id,
            user_id=user_id,
            product_ids=product_ids,
            customer_profile=customer_profile,
            permission_context=permission_context,
            trace_id=trace_id,
        )
        data = {
            "sessionId": session_id,
            "answerId": result.answer_id,
            "answerBlocks": result.answer_blocks or [],
            "citations": result.citations or [],
            "compliance": result.compliance or {},
            "trace": result.trace or {},
            "suggestedQuestions": result.suggested_questions or [],
        }
        # 落助手消息（摘要）
        preview = ""
        if data["answerBlocks"]:
            preview = str(data["answerBlocks"][0] or "")[:2000]
        append_message(session_id, "assistant", preview, answer_id=result.answer_id, citation_count=len(data["citations"]))
        return data

    # 7) 非流式
    if body.stream is False:
        try:
            data = await _run_once()
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=data))
        except Exception:
            return JSONResponse(
                status_code=200,
                content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
            )

    # 8) 流式 SSE（当前实现为“结果完成后分块推送”，后续可替换为真正流式生成）
    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            data = await _run_once()
            answer_blocks = data.get("answerBlocks") or []
            if not answer_blocks:
                answer_blocks = [""]
            for block in answer_blocks:
                for chunk in _chunk_text(str(block or "")):
                    yield _sse_event("message", {"text": chunk}).encode("utf-8")
                    await asyncio.sleep(0)
            for c in (data.get("citations") or []):
                yield _sse_event("citation", c).encode("utf-8")
                await asyncio.sleep(0)
            yield _sse_event(
                "done",
                {
                    "sessionId": data.get("sessionId"),
                    "answerId": data.get("answerId"),
                    "trace": data.get("trace") or {},
                    "suggestedQuestions": data.get("suggestedQuestions") or [],
                    "compliance": data.get("compliance") or {},
                },
            ).encode("utf-8")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("chat 流式执行异常，推送 error 事件: %s", e, exc_info=True)
            yield _sse_event(
                "error",
                {"code": int(ErrorCode.INTERNAL_ERROR), "message": message_for(ErrorCode.INTERNAL_ERROR)},
            ).encode("utf-8")

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

