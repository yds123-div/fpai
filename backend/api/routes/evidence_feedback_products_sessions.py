# -*- coding: utf-8 -*-
"""
Evidence / Feedback / Products / Sessions 路由（T031）。

GET /api/v1/evidence/{answerId}、POST /api/v1/feedback、
GET /api/v1/products/search、GET|POST /api/v1/sessions。
见 technical_design §2.2、§2.3。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_auth_context, get_current_user_id
from pkg.codes import ErrorCode, envelope, message_for

router = APIRouter(prefix="", tags=["evidence_feedback_products_sessions"])


def _permission_context(auth: Any) -> dict[str, Any]:
    return {
        "role": getattr(auth, "role", None),
        "productPoolIds": getattr(auth, "product_pool_ids", None) or [],
    }


# ---------- Evidence ----------


@router.get("/evidence/{answer_id}")
async def get_evidence(answer_id: str, user_id: str = Depends(get_current_user_id)):
    """
    按 answerId 查询证据：请求摘要、意图、数据源、检索证据片段、模型/策略版本、操作人、时间戳。
    与审计共用证据对象；仅返回当前用户所属答案，否则 40403。
    """
    answer_id = (answer_id or "").strip()
    if not answer_id:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="answerId 不能为空", data=None),
        )
    try:
        from audit import get_evidence as audit_get_evidence
        ev = audit_get_evidence(answer_id)
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    if not ev:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.ANSWER_NOT_FOUND, message=message_for(ErrorCode.ANSWER_NOT_FOUND), data=None),
        )
    if (ev.get("user_id") or "") != (user_id or ""):
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.ANSWER_NOT_FOUND, message=message_for(ErrorCode.ANSWER_NOT_FOUND), data=None),
        )
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=ev))


# ---------- Feedback ----------


class FeedbackBody(BaseModel):
    answerId: str = Field(..., min_length=1)
    rating: str = Field(...)  # useful | not_useful | inaccurate
    comment: str | None = Field(default=None)


@router.post("/feedback")
async def post_feedback(body: FeedbackBody, user_id: str = Depends(get_current_user_id)):
    """
    提交答案反馈：answerId、rating（useful/not_useful/inaccurate）、comment 可选。
    响应 data 为 { "ack": true }。
    """
    rating = (body.rating or "").strip().lower()
    if rating not in ("useful", "not_useful", "inaccurate"):
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.VALIDATION_ERROR,
                message="rating 须为 useful / not_useful / inaccurate 之一",
                data=None,
            ),
        )
    try:
        from feedback import submit_feedback
        ok = submit_feedback(
            answer_id=body.answerId.strip(),
            user_id=user_id or "",
            rating=rating,
            comment=(body.comment or "").strip() or None,
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    if not ok:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message="反馈提交失败", data=None),
        )
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data={"ack": True}))


# ---------- Products search ----------


# 产品列表领域模型编码，与 data_access 注册一致；无配置时 get_data 返回 ([], 0)
PRODUCTS_MODEL_CODE = "products"


@router.get("/products/search")
async def products_search(
    productType: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    pageSize: int = 20,
    auth=Depends(get_auth_context),
):
    """
    产品列表/筛选：productType、keyword 可选；page、pageSize 分页。
    仅返回当前用户可售且符合 productPoolIds 的产品；data 含 products[]、total。
    """
    page = max(1, page)
    pageSize = max(1, min(pageSize, 100))
    params: dict[str, Any] = {"page": page, "page_size": pageSize}
    if productType:
        params["product_type"] = productType
    if keyword:
        params["keyword"] = keyword
    try:
        from data_access import get_data
        records, total = get_data(
            model_code=PRODUCTS_MODEL_CODE,
            request_params=params,
            permission_context=_permission_context(auth),
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    return JSONResponse(
        status_code=200,
        content=envelope(
            code=ErrorCode.OK,
            message="ok",
            data={"products": records or [], "total": total or 0},
        ),
    )


# ---------- Sessions ----------


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, user_id: str = Depends(get_current_user_id)):
    """会话详情：id、user_id、product_ids、customer_profile、created_at、updated_at。仅当前用户的会话可查。"""
    session_id = (session_id or "").strip()
    if not session_id:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="sessionId 不能为空", data=None),
        )
    try:
        from orchestrator.session import get_session
        session = get_session(session_id)
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    if not session:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.SESSION_NOT_FOUND, message=message_for(ErrorCode.SESSION_NOT_FOUND), data=None),
        )
    if (session.get("user_id") or "") != (user_id or ""):
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.SESSION_NOT_FOUND, message=message_for(ErrorCode.SESSION_NOT_FOUND), data=None),
        )
    return JSONResponse(status_code=200, content=envelope(code=ErrorCode.OK, message="ok", data=session))


@router.post("/sessions")
async def create_session_api(user_id: str = Depends(get_current_user_id)):
    """创建会话；返回 data 含 sessionId（即 id）。"""
    try:
        from orchestrator.session import create_session
        session_id = create_session(user_id=user_id or "")
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    return JSONResponse(
        status_code=200,
        content=envelope(code=ErrorCode.OK, message="ok", data={"id": session_id, "sessionId": session_id}),
    )
