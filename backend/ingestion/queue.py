# -*- coding: utf-8 -*-
"""
Ingestion 任务队列：Redis List 投递文档解析/向量化任务，Worker 消费后写 Milvus。

T032：见 technical_design §3.3 Ingestion → Queue。
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from pkg.redis_client import get_client

INGESTION_QUEUE_KEY = os.getenv("INGESTION_QUEUE_KEY", "ingestion:queue")
INGESTION_QUEUE_BLOCK_TIMEOUT = int(os.getenv("INGESTION_QUEUE_BLOCK_TIMEOUT", "30"))


def push_task(
    doc_id: str,
    content: bytes,
    *,
    source: str = "",
    permission_tag: str = "",
    filename: str = "",
) -> bool:
    """
    将一条文档任务投递到队列。content 以 base64 存入 JSON 负载。

    Returns:
        是否投递成功（Redis 不可用时为 False）。
    """
    client = get_client()
    if not client:
        return False
    payload = {
        "doc_id": doc_id,
        "source": source or doc_id,
        "permission_tag": permission_tag or "default",
        "content_b64": base64.b64encode(content).decode("ascii"),
        "filename": filename or "",
    }
    try:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        client.lpush(INGESTION_QUEUE_KEY, raw)
        return True
    except Exception:
        return False


def pop_task(timeout_seconds: int | None = None) -> dict[str, Any] | None:
    """
    从队列取出一条任务（BRPOP，阻塞等待）。

    Returns:
        解析后的任务 dict（含 doc_id, source, permission_tag, content_b64, filename）；
        无任务或 Redis 不可用时返回 None。
    """
    client = get_client()
    if not client:
        return None
    timeout = timeout_seconds if timeout_seconds is not None else INGESTION_QUEUE_BLOCK_TIMEOUT
    try:
        result = client.brpop(INGESTION_QUEUE_KEY, timeout=timeout)
        if not result:
            return None
        # brpop 返回 (key, value)；Redis decode_responses=False 时 value 为 bytes
        _, value = result if isinstance(result, (list, tuple)) else (None, result)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        data = json.loads(value)
        return data
    except Exception:
        return None


def task_content_from_payload(payload: dict[str, Any]) -> bytes | None:
    """从任务负载中解码 content bytes。"""
    b64 = payload.get("content_b64")
    if not b64:
        return None
    try:
        return base64.b64decode(b64)
    except Exception:
        return None
