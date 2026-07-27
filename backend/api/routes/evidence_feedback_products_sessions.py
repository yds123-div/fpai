# -*- coding: utf-8 -*-
"""
Evidence / Feedback / Products / Sessions 路由（T031）。

GET /api/v1/evidence/{answerId}、POST /api/v1/feedback、
GET /api/v1/products/search、GET|POST /api/v1/sessions。
见 technical_design §2.2、§2.3。
"""
from __future__ import annotations

from typing import Any
import asyncio
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.deps import get_auth_context, get_current_user_id
from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import get_logger

router = APIRouter(prefix="", tags=["evidence_feedback_products_sessions"])
logger = get_logger(__name__)


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
    productCode: str | None = None,
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
    if productCode:
        params["product_code"] = productCode
    if productType:
        params["product_type"] = productType
    if keyword:
        params["keyword"] = keyword
    # 优先使用本地同步基金库（支持模糊查询）；为空时再回退到既有 data_access。
    records: list[dict[str, Any]] = []
    total: int = 0
    try:
        from products.store import search_products

        records, total = search_products(
            product_code=productCode,
            product_type=productType,
            keyword=keyword,
            page=page,
            page_size=pageSize,
        )
    except Exception:
        records, total = [], 0

    if not records and total == 0:
        try:
            from data_access import get_data

            records, total_fallback = get_data(
                model_code=PRODUCTS_MODEL_CODE,
                request_params=params,
                permission_context=_permission_context(auth),
            )
            total = int(total_fallback or 0)
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


@router.post("/products/sync")
async def products_sync(limit: int = 100):
    """
    同步基金产品数据（AkShare）到本地库。
    - 先限定最多 100 条
    """
    lim = max(1, min(int(limit or 100), 100))
    try:
        import akshare as ak
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="后端缺少 akshare 依赖，无法同步基金数据",
                data=None,
            ),
        )
    try:
        fn = getattr(ak, "fund_name_em", None)
        if not callable(fn):
            return JSONResponse(
                status_code=200,
                content=envelope(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="当前 akshare 版本不支持 fund_name_em 接口",
                    data=None,
                ),
            )
        df = fn()
        if df is None or not hasattr(df, "to_dict"):
            return JSONResponse(
                status_code=200,
                content=envelope(code=ErrorCode.SERVICE_UNAVAILABLE, message="AkShare 返回数据为空", data=None),
            )
        rows = df.to_dict(orient="records")[:lim]
        items: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            code = str(r.get("基金代码") or r.get("code") or r.get("fund_code") or "").strip()
            name = str(r.get("基金简称") or r.get("基金名称") or r.get("name") or r.get("fund_name") or "").strip()
            ptype = str(r.get("基金类型") or r.get("type") or r.get("fund_type") or "").strip()
            if not code or not name:
                continue
            items.append(
                {
                    "code": code,
                    "name": name,
                    "productType": ptype,
                    "riskLevel": "-",
                    "term": "-",
                    "source": "akshare",
                }
            )
        from products.store import upsert_products

        affected = upsert_products(items)
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.OK,
                message="ok",
                data={"limit": lim, "received": len(rows), "valid": len(items), "affected": affected},
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content=envelope(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message=f"同步基金数据失败：{e}",
                data=None,
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


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    """获取会话历史消息（按时间升序），用于页面刷新后恢复对话上下文。

    仅当前用户所属的会话可查；会话不存在返回 SESSION_NOT_FOUND。
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="sessionId 不能为空", data=None),
        )
    t0 = time.perf_counter()
    try:
        from orchestrator.session import get_session, get_recent_messages
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
    try:
        lim = max(1, min(int(limit or 50), 100))
        rows = get_recent_messages(session_id, limit=lim) or []
    except Exception:
        rows = []
    # === RCA 埋点：定位“刷新后对话消失” ===
    try:
        from pkg.mysql_client import is_configured as _mysql_is_configured
        from pkg.logger import get_logger as _get_logger
        _rca_log = _get_logger(__name__)
        if not rows:
            _rca_log.warning(
                "[RCA][sessions/messages] empty history response: session_id=%s, user_id=%s, mysql_configured=%s, requested_limit=%s",
                session_id[:8],
                (user_id or "")[:8],
                _mysql_is_configured(),
                limit,
            )
    except Exception:
        pass
    # get_recent_messages 是按 created_at 倒序返回，这里翻转为正序以便前端按顺序渲染
    items = list(reversed(rows))
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "[sessions/messages] read done elapsed_ms=%s session_id=%s item_count=%s",
        elapsed_ms,
        session_id[:8],
        len(items),
    )
    return JSONResponse(
        status_code=200,
        content=envelope(code=ErrorCode.OK, message="ok", data={"sessionId": session_id, "items": items}),
    )


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


@router.get("/sessions")
async def list_sessions(
    page: int = 1,
    pageSize: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """分页获取当前用户会话列表（包含无消息会话），按 lastMessageAt 倒序。"""
    p = max(1, int(page or 1))
    ps = max(1, min(int(pageSize or 20), 100))
    app_timeout_s = 3.0
    try:
        from orchestrator.session import list_user_sessions

        rows, total = await asyncio.wait_for(
            run_in_threadpool(
                list_user_sessions,
                user_id=user_id or "",
                page=p,
                page_size=ps,
                mysql_connect_timeout=3,
                mysql_read_timeout=5,
                mysql_write_timeout=5,
                query_timeout_ms=3000,
            ),
            timeout=app_timeout_s,
        )
        items = [
            {
                "sessionId": r.get("session_id") or "",
                "createdAt": r.get("created_at") or "",
                "lastMessageAt": r.get("last_message_at") or r.get("created_at") or "",
                "lastMessagePreview": r.get("last_message_preview"),
            }
            for r in (rows or [])
        ]
    except asyncio.TimeoutError:
        logger.warning(
            "[sessions/list] timeout, return empty list timeout_s=%.1f",
            app_timeout_s,
        )
        items = []
        total = 0
    except Exception as e:
        logger.warning(
            "[sessions/list] failed, return empty list error=%s",
            e,
            exc_info=True,
        )
        items = []
        total = 0
    return JSONResponse(
        status_code=200,
        content=envelope(
            code=ErrorCode.OK,
            message="ok",
            data={"items": items, "total": total, "page": p, "pageSize": ps},
        ),
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """删除当前用户会话（硬删除）。"""
    sid = (session_id or "").strip()
    if not sid:
        return JSONResponse(
            status_code=404,
            content=envelope(code=ErrorCode.SESSION_NOT_FOUND, message=message_for(ErrorCode.SESSION_NOT_FOUND), data=None),
        )
    t0 = time.perf_counter()
    try:
        from orchestrator.session import delete_user_session
        status = delete_user_session(sid, user_id or "")
    except Exception as e:
        logger.warning("[sessions/delete] route error=%s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("[sessions/delete] done elapsed_ms=%s session_id=%s status=%s", elapsed_ms, sid[:8], status)
    if status == "not_found":
        return JSONResponse(
            status_code=404,
            content=envelope(code=ErrorCode.SESSION_NOT_FOUND, message=message_for(ErrorCode.SESSION_NOT_FOUND), data=None),
        )
    if status == "forbidden":
        return JSONResponse(
            status_code=403,
            content=envelope(code=ErrorCode.FORBIDDEN, message=message_for(ErrorCode.FORBIDDEN), data=None),
        )
    if status != "deleted":
        return JSONResponse(
            status_code=500,
            content=envelope(code=ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR), data=None),
        )
    return JSONResponse(
        status_code=200,
        content=envelope(code=ErrorCode.OK, message="ok", data={"sessionId": sid, "deleted": True}),
    )
