# -*- coding: utf-8 -*-
"""
Ingestion Worker：消费队列任务 → 解析（MinerU）→ 分块 → 向量化 → 写 Milvus + 元数据。

T032：见 technical_design §4、architecture Document Ingestion。
"""
from __future__ import annotations

import time
from typing import Any

from pkg.logger import get_logger
from pkg.milvus_client import (
    ensure_collection,
    get_collection_name,
    insert_chunks,
)

from ingestion.chunking import chunk_text
from ingestion.queue import pop_task, task_content_from_payload

logger = get_logger(__name__)


def _get_embedding_dimension() -> int | None:
    """通过 embed 单条短文本获取向量维度；未配置时返回 None。"""
    try:
        from model_gateway import embed
        from model_gateway.llm import ModelNotConfiguredError
    except ImportError:
        return None
    try:
        vectors = embed(["dim"])
        if vectors and vectors[0]:
            return len(vectors[0])
    except Exception:
        pass
    return None


def process_one_task(timeout_seconds: int | None = None) -> bool:
    """
    从队列取一条任务并处理：解析 → 分块 → 向量化 → 写 Milvus。

    Returns:
        True 表示处理了一条任务；False 表示未取到任务或处理失败（不重试）。
    """
    payload = pop_task(timeout_seconds=timeout_seconds)
    if not payload:
        return False

    doc_id = (payload.get("doc_id") or "").strip()
    source = (payload.get("source") or doc_id or "ingestion").strip()
    permission_tag = (payload.get("permission_tag") or "default").strip()
    filename = (payload.get("filename") or "").strip()

    content = task_content_from_payload(payload)
    if not content:
        logger.warning("ingestion task missing content: doc_id=%s", doc_id)
        return True  # 已消费，不再重试

    # 1) 解析
    try:
        from parsing import parse_document_bytes
        from parsing.errors import MinerUNotAvailable
    except ImportError:
        logger.warning("parsing 模块不可用，跳过任务 doc_id=%s", doc_id)
        return True
    try:
        parsed = parse_document_bytes(
            content,
            filename=filename,
            engine="mineru",
        )
    except MinerUNotAvailable as e:
        logger.warning("MinerU 不可用，跳过任务 doc_id=%s: %s", doc_id, e)
        return True
    except Exception as e:
        logger.exception("解析失败 doc_id=%s: %s", doc_id, e)
        return True

    full_text = parsed.full_text
    if not full_text.strip():
        logger.info("文档无正文，跳过向量化 doc_id=%s", doc_id)
        return True

    # 2) 分块
    chunks = chunk_text(full_text, chunk_size=500, overlap=50)
    if not chunks:
        return True

    # 3) 向量化
    try:
        from model_gateway import embed
        from model_gateway.llm import ModelNotConfiguredError
    except ImportError:
        logger.warning("model_gateway 不可用，跳过向量化 doc_id=%s", doc_id)
        return True
    try:
        vectors = embed(chunks)
    except ModelNotConfiguredError:
        logger.warning("Embedding 未配置，跳过向量化 doc_id=%s", doc_id)
        return True
    except Exception as e:
        logger.exception("向量化失败 doc_id=%s: %s", doc_id, e)
        return True

    if not vectors or len(vectors) != len(chunks):
        logger.warning("向量数量与 chunk 不一致 doc_id=%s", doc_id)
        return True

    dim = len(vectors[0])
    if not ensure_collection(dim, collection_name=get_collection_name()):
        logger.warning("Milvus collection 确保失败，跳过写入 doc_id=%s", doc_id)
        return True

    # 4) 写 Milvus
    ts = int(time.time())
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    doc_ids = [doc_id] * len(chunks)
    sources = [source] * len(chunks)
    permission_tags = [permission_tag] * len(chunks)
    created_ats = [ts] * len(chunks)
    ok = insert_chunks(
        ids=ids,
        vectors=vectors,
        doc_ids=doc_ids,
        sources=sources,
        permission_tags=permission_tags,
        created_ats=created_ats,
        chunk_texts=chunks,
    )
    if ok:
        logger.info("ingestion 完成 doc_id=%s chunks=%s", doc_id, len(chunks))
    else:
        logger.warning("Milvus 写入失败 doc_id=%s", doc_id)
    return True


def run_worker(once: bool = False, poll_interval: float = 1.0) -> None:
    """
    循环消费队列；once=True 时只处理一条后退出。
    """
    while True:
        process_one_task(timeout_seconds=5)
        if once:
            break
        time.sleep(poll_interval)
