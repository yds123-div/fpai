# -*- coding: utf-8 -*-
"""
文档上传：投递到 ingestion 队列，由 Worker 经 MinerU 解析、分块、向量化后写 Milvus（T032）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse

from api.deps import get_auth_context
from pkg.codes import ErrorCode, envelope, message_for

from ingestion import submit_document

router = APIRouter(prefix="", tags=["documents"])

# 单文件大小上限（字节），默认 50MB
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    source: str = Query("", description="来源标识"),
    permission_tag: str = Query("", description="权限标签，检索过滤用"),
    auth=Depends(get_auth_context),
):
    """
    上传文档并投递到 ingestion 队列；Worker 将经 MinerU 解析、分块、向量化后写入 Milvus。
    响应 data 含 doc_id；后续可通过检索使用该文档。
    """
    try:
        content = await file.read()
    except Exception:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.BAD_REQUEST, message="读取文件失败", data=None),
        )
    if not content:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message="文件为空", data=None),
        )
    if len(content) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.VALIDATION_ERROR, message=f"文件超过 {MAX_UPLOAD_BYTES // (1024*1024)}MB 限制", data=None),
        )
    pt = (permission_tag or "").strip()
    if not pt and getattr(auth, "product_pool_ids", None):
        ids = auth.product_pool_ids
        pt = ids[0] if isinstance(ids, list) and ids else "default"
    if not pt:
        pt = "default"
    doc_id = submit_document(
        content,
        source=(source or "").strip() or (file.filename or "upload"),
        permission_tag=pt,
        filename=file.filename or "",
    )
    if not doc_id:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.SERVICE_UNAVAILABLE, message="队列不可用，请稍后重试", data=None),
        )
    return JSONResponse(
        status_code=200,
        content=envelope(code=ErrorCode.OK, message="已投递，将由 Worker 解析并写入向量库", data={"doc_id": doc_id}),
    )
