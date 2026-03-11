# -*- coding: utf-8 -*-
"""
Compare / Recommend / Report 路由（T030）。

POST /api/v1/compare、POST /api/v1/recommend、POST /api/v1/report/generate：
请求/响应契约见 technical_design §2.2、§2.3；编排调用 agents 层 query_*。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
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


def _citations_list(raw: Any) -> list[dict[str, Any]]:
    if not raw or not isinstance(raw, list):
        return []
    return [_jsonable(c) for c in raw]


# ---------- Compare ----------


class CompareBody(BaseModel):
    productIds: list[str] = Field(..., min_length=2)
    dimensionTemplateId: str | None = Field(default=None)


@router.post("/compare")
async def compare(body: CompareBody, request: Request, auth=Depends(get_auth_context)):
    """
    多产品对比：请求体 productIds（≥2）、可选 dimensionTemplateId；
    响应 data 含 comparisonTable、summary、citations[]、compliance、trace。
    """
    trace_id = (request.headers.get("X-Request-Id") or "").strip() or None
    try:
        from agents.product_compare.agent import query_product_compare

        result = await asyncio.to_thread(
            query_product_compare,
            body.productIds,
            permission_context=_permission_context(auth),
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
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


# ---------- Recommend ----------


class RecommendBody(BaseModel):
    customerProfile: dict[str, Any] | str | None = Field(default=None)
    topN: int | None = Field(default=5, ge=1, le=20)


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
    try:
        from agents.product_recommend.agent import query_product_recommend

        result = await asyncio.to_thread(
            query_product_recommend,
            profile_str,
            top_n=body.topN or 5,
            permission_context=_permission_context(auth),
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    data = {
        "products": result.get("products") or [],
        "disclaimers": "以上推荐仅供参考，不构成投资建议；请以产品说明书与销售文件为准。",
        "citations": [],
        "compliance": {"action": "pass"},
        "trace": _trace(trace_id),
    }
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=data))


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
