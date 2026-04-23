# -*- coding: utf-8 -*-
"""
Chat 路由：POST /api/v1/chat（T029）。

- 支持非流式（统一 envelope）与流式（SSE）。
- 会话：无 sessionId 时隐式创建；写回 productIds/customerProfile 到会话上下文（Redis，若可用）。
"""
from __future__ import annotations

import asyncio
import json
import uuid
import time
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
    get_recent_messages,
)

router = APIRouter(prefix="", tags=["chat"])
logger = get_logger(__name__)


class ChatBody(BaseModel):
    sessionId: str | None = Field(default=None)
    message: str = Field(default="")
    productIds: list[str] | None = Field(default=None)
    customerProfile: dict[str, Any] | str | None = Field(default=None)
    stream: bool | None = Field(default=True)
    model_id: int | None = Field(default=None, description="模型配置 ID（来自模型管理）")
    model: str | None = Field(default=None, description="模型名称（覆盖 LLM_MODEL）")
    knowledge_base_id: str | None = Field(default=None, description="智能对话选中的知识库 UUID（用于其它类问题检索）")
    showThinking: bool | None = Field(
        default=False,
        description="是否展示模型推理过程（可能输出 <think>...</think>）",
    )
    direct_stream: bool | None = Field(
        default=False,
        description="是否启用直连 OpenAI 兼容接口的真正流式（默认关闭；开启后将绕过 5-Agent 编排）",
    )


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


async def _stream_openai_chat(
    base_url: str,
    api_key: str | None,
    model_name: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 5000,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    通过 OpenAI 兼容接口做真正流式对话（/chat/completions, stream=true），逐个 yield 文本片段。
    """
    try:
        import httpx
        import json as _json
    except ImportError:
        return

    bu = (base_url or "").rstrip("/")
    if not bu.endswith("/v1"):
        bu = bu + "/v1"
    url = bu + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        # 过滤 <think>...</think>（流式 token 可能拆标签）
        in_think = False
        carry = ""

        def _filter_think(delta: str) -> str:
            nonlocal in_think, carry
            if not delta:
                return ""
            s = carry + delta
            carry = ""
            out_parts: list[str] = []
            i = 0
            while i < len(s):
                if not in_think:
                    j = s.find("<think>", i)
                    if j == -1:
                        out_parts.append(s[i:])
                        break
                    out_parts.append(s[i:j])
                    in_think = True
                    i = j + len("<think>")
                else:
                    k = s.find("</think>", i)
                    if k == -1:
                        break
                    in_think = False
                    i = k + len("</think>")

            tail = s[max(0, len(s) - 8) :]
            if not in_think:
                if "<think" in tail and "<think>" not in tail:
                    p = s.rfind("<think")
                    if p != -1 and p >= len(s) - 8:
                        carry = s[p:]
                        joined = "".join(out_parts)
                        return joined[: max(0, len(joined) - len(carry))]
                if "</think" in tail and "</think>" not in tail:
                    p = s.rfind("</think")
                    if p != -1 and p >= len(s) - 8:
                        carry = s[p:]
                        joined = "".join(out_parts)
                        return joined[: max(0, len(joined) - len(carry))]
            return "".join(out_parts)

        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        break
                    try:
                        obj = _json.loads(data_str)
                    except Exception:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        filtered = _filter_think(str(content))
                        if filtered:
                            yield filtered
        except Exception as e:
            logger.warning("stream_openai_chat failed: %s", e)
            return


def _build_openai_messages_from_history(
    session_id: str,
    current_user_text: str,
    *,
    limit: int = 12,
) -> list[dict[str, str]]:
    """
    从 MySQL messages（content_summary）构造 OpenAI 兼容 messages。
    仅用于“真正流式”直连模式；编排器模式仍由 AgentScope 自己处理上下文/工具调用。
    """
    history = get_recent_messages(session_id, limit=limit) or []
    # get_recent_messages 是倒序（最新在前），这里反过来拼成对话顺序
    history = list(reversed(history))
    msgs: list[dict[str, str]] = [
        {
            "role": "system",
            "content": "你是金融产品解析智能体助手。请用简洁、结构化的方式回答用户问题。",
        }
    ]
    for h in history:
        role = (h.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = (h.get("content_summary") or "").strip()
        if not content:
            continue
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": (current_user_text or "").strip()})
    return msgs


@router.post("/chat")
async def chat(body: ChatBody, request: Request, auth=Depends(get_auth_context)):
    """
    多轮对话入口：支持 stream（SSE）与非流式。
    - stream=true：返回 text/event-stream，事件 message/citation/done/error。
    - stream=false：返回 JSON envelope，data 含 answerId、answerBlocks、citations、compliance、trace、suggestedQuestions。
    """
    # ========== 性能监控：API 入口 ==========
    import time
    t_api_start = time.perf_counter()
    trace_id_temp = (request.headers.get("X-Request-Id") or "").strip() or "unknown"
    logger.info(f"📨 [{trace_id_temp[:8]}] /chat 请求 stream={body.stream}")
    
    # 1) 会话管理与权限上下文并行处理
    user_id = getattr(auth, "user_id", "") or ""
    session_id = (body.sessionId or "").strip() or None
    
    # 并行任务1: 会话验证/创建
    async def _handle_session() -> str | None:
        """验证现有会话或创建新会话（使用 to_thread 避免阻塞）。
        
        Returns:
            str | None: 会话ID，如果会话不存在则返回 None
        """
        nonlocal session_id
        if session_id:
            result = await asyncio.to_thread(get_session, session_id)
            if not result:
                return None
        else:
            session_id = await asyncio.to_thread(create_session, user_id=user_id)
        return session_id
    
    # 并行任务2: 准备权限上下文（不依赖会话）
    async def _prepare_permission_context() -> dict[str, Any]:
        """准备权限上下文字典。
        
        Returns:
            dict[str, Any]: 包含 role 和 productPoolIds 的权限上下文
        """
        return {
            "role": getattr(auth, "role", None),
            "productPoolIds": getattr(auth, "product_pool_ids", None) or [],
        }
    
    # 并行任务3: 准备 traceId（不依赖会话）
    async def _prepare_trace_id() -> str | None:
        """从请求头提取 traceId。
        
        Returns:
            str | None: traceId 或 None
        """
        return (request.headers.get("X-Request-Id") or "").strip() or None
    
    # 并行任务4: 准备消息文本（不依赖会话）
    async def _prepare_message() -> str:
        """提取并清理用户消息文本。
        
        Returns:
            str: 清理后的消息文本
        """
        return (body.message or "").strip()
    
    # 并行执行
    t_now = time.perf_counter()
    # 并行初始化开始不记录日志
    
    session_result, permission_context, trace_id, msg = await asyncio.gather(
        _handle_session(),
        _prepare_permission_context(),
        _prepare_trace_id(),
        _prepare_message(),
    )
    
    t_now = time.perf_counter()
    if t_now - t_api_start > 2.0:  # 只记录超过2秒的初始化
        logger.info(f"⏱️  [{trace_id_temp[:8]}] 并行初始化耗时 {t_now - t_api_start:.2f}s")
    
    # 检查会话是否有效
    if session_result is None:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.SESSION_NOT_FOUND, message=message_for(ErrorCode.SESSION_NOT_FOUND), data=None),
        )

    # 2) 更新会话上下文（写回）+ 落用户消息 并行
    t_now = time.perf_counter()
    # 会话上下文更新开始不记录日志
    
    customer_profile_str = _stringify_customer_profile(body.customerProfile)
    
    # 并行任务: 更新会话上下文 + 落用户消息
    await asyncio.gather(
        asyncio.to_thread(
            update_session_context,
            session_id,
            product_ids=body.productIds if body.productIds is not None else None,
            customer_profile=customer_profile_str if body.customerProfile is not None else None,
        ),
        asyncio.to_thread(append_message, session_id, "user", msg[:2000]),
    )
    
    t_now = time.perf_counter()
    # 会话上下文更新完成不记录日志（通常很快）

    # 3) 供编排使用的会话上下文（合并 request + session）
    ctx = get_session_context_for_orchestration(session_id)
    product_ids = body.productIds if body.productIds is not None else ctx.get("product_ids")
    customer_profile = customer_profile_str if body.customerProfile is not None else ctx.get("customer_profile")

    async def _run_once() -> dict[str, Any]:
        # 若传入 model_id，则从 MySQL 读取模型配置（base_url/api_key/model_name），用于本轮覆盖
        base_url_override: str | None = None
        api_key_override: str | None = None
        model_name_override: str | None = (body.model or "").strip() or None
        if body.model_id:
            try:
                from models.store import get_model_by_id

                cfg = get_model_by_id(int(body.model_id))
                if cfg and int(cfg.get("enabled") or 0) == 1:
                    base_url_override = (cfg.get("base_url") or "").strip() or None
                    api_key_override = (cfg.get("api_key") or "").strip() or None
                    model_name_override = (cfg.get("model_name") or "").strip() or model_name_override
            except Exception:
                pass
        result = await run_chat_turn_async(
            msg,
            session_id=session_id,
            user_id=user_id,
            product_ids=product_ids,
            customer_profile=customer_profile,
            permission_context=permission_context,
            trace_id=trace_id,
            model_name=model_name_override,
            base_url=base_url_override,
            api_key=api_key_override,
            knowledge_base_id=(body.knowledge_base_id or "").strip() or None,
            show_thinking=bool(body.showThinking),
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
        append_message(session_id, "assistant", preview, answer_id=result.answer_id, citation_count=len(data["citations"]), full_content=result.raw_reply or None, structured_outputs=result.structured_outputs or None)
        return data

    # 7) 非流式
    if body.stream is False:
        try:
            t_now = time.perf_counter()
            # 编排执行开始不记录日志
            
            data = await _run_once()
            
            t_now = time.perf_counter()
            total_time = t_now - t_api_start
            logger.info(f"✅ [{trace_id_temp[:8]}] /chat 完成 总耗时 {total_time:.2f}s")
            
            return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=data))
        except Exception:
            return JSONResponse(
                status_code=200,
                content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
            )

    # 8) 流式 SSE（当前实现为“结果完成后分块推送”，后续可替换为真正流式生成）
    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            stream_started_at = time.perf_counter()
            last_message_delta_at: float | None = None
            structured_emitted_at: float | None = None
            # 若传入 model_id 且模型配置含 base_url，则走 OpenAI 兼容“真正流式”直连模式
            base_url_override: str | None = None
            api_key_override: str | None = None
            model_name_override: str | None = (body.model or "").strip() or None
            if body.model_id:
                try:
                    from models.store import get_model_by_id

                    cfg = get_model_by_id(int(body.model_id))
                    if cfg and int(cfg.get("enabled") or 0) == 1:
                        base_url_override = (cfg.get("base_url") or "").strip() or None
                        api_key_override = (cfg.get("api_key") or "").strip() or None
                        model_name_override = (cfg.get("model_name") or "").strip() or model_name_override
                except Exception:
                    pass

            if (body.direct_stream is True) and base_url_override and model_name_override:
                answer_id = uuid.uuid4().hex
                streaming_text = ""
                openai_messages = _build_openai_messages_from_history(session_id, msg, limit=12)
                logger.info(
                    "[SSE_DEBUG][%s] emit message_start t=%.3fs mode=direct_stream",
                    answer_id[:8],
                    time.perf_counter() - stream_started_at,
                )
                yield _sse_event("message_start", {"sessionId": session_id, "answerId": answer_id}).encode("utf-8")
                async for t in _stream_openai_chat(
                    base_url=base_url_override,
                    api_key=api_key_override,
                    model_name=model_name_override,
                    messages=openai_messages,
                ):
                    streaming_text += t
                    last_message_delta_at = time.perf_counter()
                    yield _sse_event("message_delta", {"sessionId": session_id, "answerId": answer_id, "text": t}).encode("utf-8")
                    await asyncio.sleep(0)

                preview = (streaming_text or "")[:2000]
                append_message(session_id, "assistant", preview, answer_id=answer_id, citation_count=0, full_content=streaming_text or None)
                yield _sse_event(
                    "done",
                    {
                        "sessionId": session_id,
                        "answerId": answer_id,
                        "trace": {"mode": "direct_stream"},
                        "suggestedQuestions": [],
                        "compliance": {"action": "pass"},
                    },
                ).encode("utf-8")
                logger.info(
                    "[SSE_DEBUG][%s] emit done t=%.3fs last_delta_gap=%.3fs",
                    answer_id[:8],
                    time.perf_counter() - stream_started_at,
                    (time.perf_counter() - last_message_delta_at) if last_message_delta_at else -1.0,
                )
            else:
                # 编排器（带进度事件 + 可选 token 级流式输出）
                q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

                async def _emit(ev: str, payload: Any):
                    await q.put((ev, payload))

                async def _progress(stage: str, **kwargs):
                    """接收编排器的进度事件"""
                    message = kwargs.get("message", "")
                    await _emit("status", {"stage": stage, "message": message})

                async def _stream_token(t: str):
                    # 仅推送增量 token
                    await _emit("message_delta", {"text": t})

                async def _runner():
                    # 若传入 model_id，则从 MySQL 读取模型配置（base_url/api_key/model_name），用于本轮覆盖
                    base_url_ov: str | None = None
                    api_key_ov: str | None = None
                    model_name_ov: str | None = (body.model or "").strip() or None
                    if body.model_id:
                        try:
                            from models.store import get_model_by_id

                            cfg2 = get_model_by_id(int(body.model_id))
                            if cfg2 and int(cfg2.get("enabled") or 0) == 1:
                                base_url_ov = (cfg2.get("base_url") or "").strip() or None
                                api_key_ov = (cfg2.get("api_key") or "").strip() or None
                                model_name_ov = (cfg2.get("model_name") or "").strip() or model_name_ov
                        except Exception:
                            pass
                    stream_answer_id = uuid.uuid4().hex
                    await _progress("accepted")
                    await _emit("message_start", {"sessionId": session_id, "answerId": stream_answer_id})
                    result = await run_chat_turn_async(
                        msg,
                        session_id=session_id,
                        user_id=user_id,
                        product_ids=product_ids,
                        customer_profile=customer_profile,
                        permission_context=permission_context,
                        trace_id=trace_id,
                        model_name=model_name_ov,
                        base_url=base_url_ov,
                        api_key=api_key_ov,
                        knowledge_base_id=(body.knowledge_base_id or "").strip() or None,
                        show_thinking=bool(body.showThinking),
                        progress_callback=_progress,
                        stream_callback=_stream_token,
                        answer_id=stream_answer_id,
                    )
                    data = {
                        "sessionId": session_id,
                        "answerId": result.answer_id,
                        "answerBlocks": result.answer_blocks or [],
                        "citations": result.citations or [],
                        "compliance": result.compliance or {},
                        "trace": result.trace or {},
                        "suggestedQuestions": result.suggested_questions or [],
                        "structuredOutputs": getattr(result, "structured_outputs", None) or [],
                    }
                    # 若未走 token 流式（比如没有 base_url），此处补发一次性文本（分块）
                    answer_blocks = data.get("answerBlocks") or []
                    if answer_blocks:
                        # stream_callback 可能已经发过 token；为了避免重复，只有当本轮未产生任何 message 时才补发
                        pass
                    preview2 = ""
                    if data["answerBlocks"]:
                        preview2 = (result.raw_reply or str(data["answerBlocks"][0] or ""))[:2000]
                    append_message(session_id, "assistant", preview2, answer_id=result.answer_id, citation_count=len(data["citations"]), full_content=result.raw_reply or None, structured_outputs=result.structured_outputs or None)
                    # done/citation 统一在此处发
                    if data.get("structuredOutputs"):
                        structured_emitted_at = time.perf_counter()
                        logger.info(
                            "[SSE_DEBUG][%s] queue structured_update t=%.3fs structured_count=%d",
                            str(data.get("answerId") or "")[:8],
                            structured_emitted_at - stream_started_at,
                            len(data.get("structuredOutputs") or []),
                        )
                        await _emit(
                            "structured_update",
                            {
                                "sessionId": data.get("sessionId"),
                                "answerId": data.get("answerId"),
                                "structuredOutputs": data.get("structuredOutputs") or [],
                            },
                        )
                    for c in (data.get("citations") or []):
                        await _emit("citation", c)
                    await _emit(
                        "done",
                        {
                            "sessionId": data.get("sessionId"),
                            "answerId": data.get("answerId"),
                            "trace": data.get("trace") or {},
                            "suggestedQuestions": data.get("suggestedQuestions") or [],
                            "compliance": data.get("compliance") or {},
                            "answerBlocks": data.get("answerBlocks") or [],
                            "structuredOutputs": data.get("structuredOutputs") or [],
                        },
                    )
                    logger.info(
                        "[SSE_DEBUG][%s] queue done t=%.3fs last_delta_gap=%.3fs structured_before_done_gap=%.3fs",
                        str(data.get("answerId") or "")[:8],
                        time.perf_counter() - stream_started_at,
                        (time.perf_counter() - last_message_delta_at) if last_message_delta_at else -1.0,
                        (time.perf_counter() - structured_emitted_at) if structured_emitted_at else -1.0,
                    )
                    await _emit("__end__", None)

                runner_task = asyncio.create_task(_runner())

                sent_any_message = False
                while True:
                    ev, payload = await q.get()
                    if ev == "__end__":
                        break
                    if ev == "message_start":
                        yield _sse_event("message_start", payload).encode("utf-8")
                        await asyncio.sleep(0)
                        continue
                    if ev == "message":
                        sent_any_message = True
                        yield _sse_event("message", payload).encode("utf-8")
                        await asyncio.sleep(0)
                        continue
                    if ev == "message_delta":
                        sent_any_message = True
                        last_message_delta_at = time.perf_counter()
                        yield _sse_event("message_delta", payload).encode("utf-8")
                        await asyncio.sleep(0)
                        continue
                    if ev == "status":
                        # 进度事件（前端可选显示；不影响现有 message/citation/done 处理）
                        yield _sse_event("status", payload).encode("utf-8")
                        await asyncio.sleep(0)
                        continue
                    if ev == "citation":
                        yield _sse_event("citation", payload).encode("utf-8")
                        await asyncio.sleep(0)
                        continue
                    if ev == "structured_update":
                        structured_emitted_at = time.perf_counter()
                        logger.info(
                            "[SSE_DEBUG][%s] emit structured_update t=%.3fs",
                            str((payload or {}).get("answerId") or "")[:8],
                            structured_emitted_at - stream_started_at,
                        )
                        yield _sse_event("structured_update", payload).encode("utf-8")
                        await asyncio.sleep(0)
                        continue
                    if ev == "done":
                        # 若没有任何 token 级 message（比如未配置 base_url），则把最终 answerBlocks 分块推送一次
                        if not sent_any_message:
                            for block in (payload.get("answerBlocks") or [""]):
                                for chunk in _chunk_text(str(block or "")):
                                    yield _sse_event(
                                        "message_delta",
                                        {
                                            "sessionId": payload.get("sessionId"),
                                            "answerId": payload.get("answerId"),
                                            "text": chunk,
                                        },
                                    ).encode("utf-8")
                                    await asyncio.sleep(0)
                        yield _sse_event(
                            "done",
                            {
                                "sessionId": payload.get("sessionId"),
                                "answerId": payload.get("answerId"),
                                "trace": payload.get("trace") or {},
                                "suggestedQuestions": payload.get("suggestedQuestions") or [],
                                "compliance": payload.get("compliance") or {},
                                "structuredOutputs": payload.get("structuredOutputs") or [],
                            },
                        ).encode("utf-8")
                        logger.info(
                            "[SSE_DEBUG][%s] emit done t=%.3fs last_delta_gap=%.3fs structured_before_done_gap=%.3fs",
                            str((payload or {}).get("answerId") or "")[:8],
                            time.perf_counter() - stream_started_at,
                            (time.perf_counter() - last_message_delta_at) if last_message_delta_at else -1.0,
                            (time.perf_counter() - structured_emitted_at) if structured_emitted_at else -1.0,
                        )
                        await asyncio.sleep(0)
                        continue

                try:
                    await runner_task
                except Exception:
                    pass
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

