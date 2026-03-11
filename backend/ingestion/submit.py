# -*- coding: utf-8 -*-
"""
文档接入：提交文档到 ingestion 队列，由 Worker 解析、分块、向量化后写 Milvus。

T032：文档上传 → 经 MinerU 解析 → 分块 → 向量化任务投递（队列）；Worker 消费后写 Milvus + 元数据。
"""
from __future__ import annotations

import uuid

from ingestion.queue import push_task


def submit_document(
    content: bytes,
    *,
    doc_id: str | None = None,
    source: str = "",
    permission_tag: str = "",
    filename: str = "",
) -> str | None:
    """
    将文档投递到 ingestion 队列，异步由 Worker 解析并写入 Milvus。

    Args:
        content: 文件二进制内容（如 PDF）。
        doc_id: 文档唯一 ID；不传则自动生成。
        source: 来源标识，检索结果 citation 用；默认与 doc_id 一致。
        permission_tag: 权限标签，检索时按 permission_tag 过滤；默认 "default"。
        filename: 原始文件名，解析与日志用。

    Returns:
        本次任务的 doc_id；Redis 不可用时返回 None。
    """
    doc_id = (doc_id or "").strip() or uuid.uuid4().hex
    if not content:
        return None
    ok = push_task(
        doc_id=doc_id,
        content=content,
        source=source or doc_id,
        permission_tag=permission_tag or "default",
        filename=filename or "",
    )
    return doc_id if ok else None
