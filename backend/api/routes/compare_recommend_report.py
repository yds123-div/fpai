# -*- coding: utf-8 -*-
"""
Compare / Recommend / Report 路由（T030）。

POST /api/v1/compare、POST /api/v1/recommend、POST /api/v1/report/generate：
请求/响应契约见 technical_design §2.2、§2.3；编排调用 agents 层 query_*。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for

router = APIRouter(prefix="", tags=["compare_recommend_report"])


def _permission_context(auth: Any) -> dict[str, Any]:
    return {
        "role": getattr(auth, "role", None),
        "productPoolIds": getattr(auth, "product_pool_ids", None) or [],
    }


def _trace(trace_id: str | None) -> dict[str, Any]:
    return {"traceId": trace_id or uuid.uuid4().hex}


def _jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        return obj.to_dict()
    return obj


def _sse_event(event: str, data: Any) -> str:
    payload = json.dumps(_jsonable(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _chunk_text(text: str, chunk_size: int = 300) -> list[str]:
    content = (text or "").strip()
    if not content:
        return [""]
    if len(content) <= chunk_size:
        return [content]
    out: list[str] = []
    i = 0
    while i < len(content):
        out.append(content[i : i + chunk_size])
        i += chunk_size
    return out


def _citations_list(raw: Any) -> list[dict[str, Any]]:
    if not raw or not isinstance(raw, list):
        return []
    return [_jsonable(c) for c in raw]


# ---------- Compare ----------


class CompareBody(BaseModel):
    productIds: list[str] = Field(..., min_length=2)
    dimensionTemplateId: str | None = Field(default=None)


def _validate_product_ids(ids: list[str]) -> list[str]:
    normalized = [str(x or "").strip() for x in (ids or []) if str(x or "").strip()]
    if len(normalized) < 2:
        raise ValueError("请至少提供 2 个基金代码")
    if len(normalized) > 5:
        raise ValueError("最多支持 5 个基金代码")
    for x in normalized:
        if not (x.isdigit() and len(x) == 6):
            raise ValueError(f"基金代码格式错误：{x}（需为 6 位数字）")
    return normalized


@router.post("/compare")
async def compare(body: CompareBody, request: Request, auth=Depends(get_auth_context)):
    """
    多产品对比：请求体 productIds（≥2）、可选 dimensionTemplateId；
    响应 data 含 comparisonTable、summary、citations[]、compliance、trace。
    """
    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None
    try:
        ids = _validate_product_ids(body.productIds)
    except ValueError as e:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message=str(e), data=None),
        )
    try:
        # 使用新的 fund_agent_framework 调用产品对比
        from agents.fund_agent_framework import run_agent_query
        
        # 构造产品对比问题
        product_ids_str = "、".join(ids)
        question = f"请对比分析以下基金产品：{product_ids_str}"
        
        result = await asyncio.to_thread(
            run_agent_query,
            question=question,
            permission_context=_permission_context(auth),
        )
    except Exception as e:
        logger.exception("产品对比失败")
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=f"产品对比失败: {str(e)}", data=None),
        )
    data = {
        "comparisonTable": result.get("comparison_table") or [],
        "summary": result.get("summary") or "",
        "citations": [],  # 对比智能体当前未返回 citations，预留
        "compliance": {"action": "pass"},
        "trace": _trace(trace_id),
    }
    if body.dimensionTemplateId:
        data["dimensionTemplateId"] = body.dimensionTemplateId
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=data))


@router.post("/compare/stream")
async def compare_stream(body: CompareBody, request: Request, auth=Depends(get_auth_context)):
    """
    产品对比流式接口：调用产品对比 Agent，按 SSE 事件 message/done/error 推送。
    """
    try:
        ids = _validate_product_ids(body.productIds)
    except ValueError as e:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message=str(e), data=None),
        )

    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None
    permission_context = _permission_context(auth)

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            from agents.fund_agent.product_compare.agent import ProductCompareAgent
            from agents.fund_agent.runtime import AgentRunContext

            q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

            async def _stream_token(token: str):
                await q.put(("message", {"text": token}))

            async def _runner():
                agent = ProductCompareAgent()
                ctx = AgentRunContext(
                    permission_context=permission_context,
                    product_ids=ids,
                    stream_callback=_stream_token,
                    show_thinking=False,
                )
                question = f"请对以下基金代码进行对比分析：{'、'.join(ids)}"
                text = await agent.run(question, ctx)
                await q.put(("done", {"text": text or ""}))
                await q.put(("__end__", None))

            runner_task = asyncio.create_task(_runner())
            sent_any_message = False
            while True:
                ev, payload = await q.get()
                if ev == "__end__":
                    break
                if ev == "message":
                    sent_any_message = True
                    yield _sse_event("message", payload).encode("utf-8")
                    await asyncio.sleep(0)
                    continue
                if ev == "done":
                    if not sent_any_message:
                        for chunk in _chunk_text(str(payload.get("text") or "")):
                            yield _sse_event("message", {"text": chunk}).encode("utf-8")
                            await asyncio.sleep(0)
                    yield _sse_event(
                        "done",
                        {
                            "trace": _trace(trace_id),
                            "compliance": {"action": "pass"},
                        },
                    ).encode("utf-8")
                    await asyncio.sleep(0)
                    continue

            try:
                await runner_task
            except Exception:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
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


# ---------- Recommend ----------


class RecommendBody(BaseModel):
    customerProfile: dict[str, Any] | str | None = Field(default=None)
    topN: int | None = Field(default=5, ge=1, le=10)


def _stringify_profile(profile: dict[str, Any] | str | None) -> str:
    if profile is None:
        return ""
    if isinstance(profile, str):
        return profile.strip()
    import json
    try:
        return json.dumps(profile, ensure_ascii=False)
    except Exception:
        return str(profile)


def _parse_recommend_text(text: str) -> tuple[list[dict[str, Any]], str]:
    """
    将 ProductRecommendAgent 的纯文本输出尽量解析为结构化 products。
    """
    disclaimers = "基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议。"
    if not text:
        return [], disclaimers

    s = str(text)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    header_re = re.compile(r"^(\d+)\.\s*(.+?)（(.+?)）\s*$")

    products: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    collecting_reason = False

    def _flush():
        nonlocal cur, collecting_reason
        if cur is not None:
            cur["reason"] = (cur.get("reason") or "").strip()
            cur["tags"] = (cur.get("tags") or "").strip()
            products.append(cur)
        cur = None
        collecting_reason = False

    for ln in lines:
        m = header_re.match(ln)
        if m:
            _flush()
            cur = {
                "name": (m.group(2) or "").strip(),
                "id": (m.group(3) or "").strip(),
                "reason": "",
                "tags": "",
            }
            collecting_reason = False
            continue

        if cur is None:
            continue

        if ln.startswith("推荐原因：") or ln.startswith("推荐原因:"):
            collecting_reason = True
            cur["reason"] = (ln.split("：", 1)[-1] if "：" in ln else ln.split(":", 1)[-1]).strip()
            continue

        if collecting_reason:
            if ln.startswith("适配标签：") or ln.startswith("适配标签:"):
                collecting_reason = False
                cur["tags"] = (ln.split("：", 1)[-1] if "：" in ln else ln.split(":", 1)[-1]).strip()
                continue
            # 原因可能跨行：把后续行拼接进 reason
            if cur.get("reason"):
                cur["reason"] = f"{cur['reason']}{ln}"
            else:
                cur["reason"] = ln
            continue

        if ln.startswith("适配标签：") or ln.startswith("适配标签:"):
            cur["tags"] = (ln.split("：", 1)[-1] if "：" in ln else ln.split(":", 1)[-1]).strip()
            continue

    _flush()
    return products, disclaimers


@router.post("/recommend")
async def recommend(body: RecommendBody, request: Request, auth=Depends(get_auth_context)):
    """
    产品推荐：请求体 customerProfile（期限、流动性、风险偏好等）、可选 topN（默认 5）；
    响应 data 含 products[]、disclaimers、citations[]、compliance、trace。
    """
    profile_str = _stringify_profile(body.customerProfile)
    if not profile_str:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="请提供 customerProfile（客户画像/需求描述）", data=None),
        )
    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None
    top_n = int(body.topN or 5)
    top_n = max(1, min(10, top_n))
    try:
        from agents.fund_agent.product_recommend.agent import ProductRecommendAgent
        from agents.fund_agent.runtime import AgentRunContext

        agent = ProductRecommendAgent()
        permission_context = _permission_context(auth)
        ctx = AgentRunContext(permission_context=permission_context, customer_profile=profile_str, show_thinking=False)
        question = f"客户画像：{profile_str}\n目标推荐数量：{top_n}"
        text = await agent.run(question, ctx)
        products, disclaimers = _parse_recommend_text(text or "")
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    data = {"products": products or [], "disclaimers": disclaimers, "citations": [], "compliance": {"action": "pass"}, "trace": _trace(trace_id)}
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=data))


@router.post("/recommend/stream")
async def recommend_stream(body: RecommendBody, request: Request, auth=Depends(get_auth_context)):
    """
    产品推荐流式接口：调用 fund_agent.product_recommend Agent，按 SSE 事件 message/done/error 推送。
    """
    profile_str = _stringify_profile(body.customerProfile)
    if not profile_str:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="请提供 customerProfile（客户画像/需求描述）", data=None),
        )

    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None
    top_n = int(body.topN or 5)
    top_n = max(1, min(10, top_n))
    permission_context = _permission_context(auth)

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            from agents.fund_agent.product_recommend.agent import ProductRecommendAgent
            from agents.fund_agent.runtime import AgentRunContext

            # 立即回传首条 message：避免前端“无任何输出”的体感问题
            yield _sse_event("message", {"text": "正在生成推荐，请稍候…\n"}).encode("utf-8")

            q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
            sent_any_message = False

            async def _stream_token(token: str):
                await q.put(("message", {"text": token}))

            async def _runner():
                agent = ProductRecommendAgent()
                ctx = AgentRunContext(
                    permission_context=permission_context,
                    customer_profile=profile_str,
                    stream_callback=_stream_token,
                    show_thinking=False,
                )
                question = f"客户画像：{profile_str}\n目标推荐数量：{top_n}"
                text = await agent.run(question, ctx)
                await q.put(("done", {"text": text or ""}))
                await q.put(("__end__", None))

            runner_task = asyncio.create_task(_runner())
            while True:
                ev, payload = await q.get()
                if ev == "__end__":
                    break
                if ev == "message":
                    sent_any_message = True
                    yield _sse_event("message", payload).encode("utf-8")
                    await asyncio.sleep(0)
                    continue
                if ev == "done":
                    if not sent_any_message:
                        for chunk in _chunk_text(str(payload.get("text") or "")):
                            yield _sse_event("message", {"text": chunk}).encode("utf-8")
                            await asyncio.sleep(0)
                    yield _sse_event(
                        "done",
                        {"trace": _trace(trace_id), "compliance": {"action": "pass"}},
                    ).encode("utf-8")
                    await asyncio.sleep(0)
                    continue

            try:
                await runner_task
            except Exception:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            yield _sse_event(
                "error",
                {"code": int(ErrorCode.INTERNAL_ERROR), "message": message_for(ErrorCode.INTERNAL_ERROR)},
            ).encode("utf-8")

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------- Report generate ----------


class ReportGenerateBody(BaseModel):
    templateId: str | None = Field(default=None)
    timeRange: str | None = Field(default=None)
    topic: str | None = Field(default=None)


def _report_demand(body: ReportGenerateBody) -> str:
    parts = []
    if body.templateId:
        parts.append(body.templateId)
    if body.timeRange:
        parts.append(body.timeRange)
    if body.topic:
        parts.append(body.topic)
    return " ".join(parts).strip() or "财富周报/市场解读"


@router.post("/report/generate")
async def report_generate(body: ReportGenerateBody, request: Request, auth=Depends(get_auth_context)):
    """
    报告生成：请求体 templateId（周报/月报/市场解读等）、timeRange、topic 可选；
    响应 data 含 reportBlocks[]、citations[]、trace。
    """
    demand = _report_demand(body)
    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None
    try:
        from agents.report_generate.agent import query_report_generate

        result = await asyncio.to_thread(
            query_report_generate,
            demand,
            permission_context=_permission_context(auth),
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    citations = result.get("citations") or []
    data = {
        "reportBlocks": result.get("report_blocks") or [],
        "citations": _citations_list(citations),
        "compliance": {"action": "pass"},
        "trace": _trace(trace_id),
    }
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=data))
