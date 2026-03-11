"""
FAQ 检索层：query → Embedding → Milvus TopK 相似 → 回表 MySQL 取 answer → 返回 FAQHit 列表。

与 faq_design.md 一致。
"""
from __future__ import annotations

from pkg.logger import get_logger
logger = get_logger(__name__)

from pkg.milvus_client import (
    get_client,
    search_with_filter,
    FAQ_COLLECTION_NAME,
    FIELD_DOC_ID,
    FIELD_CHUNK_TEXT,
)

from agents.faq.store import get_faq_by_ids, FAQHit



SOURCE_FAQ = "faq"


def search_faq(query: str, top_k: int = 5) -> list[FAQHit]:
    """
    向量检索 TopK 相似 FAQ：query 向量化 → Milvus fpai_faq 检索 → 按 doc_id 回表 MySQL 取完整 FAQ。
    """
    if not query or not query.strip():
        return []
    try:
        from model_gateway import embed, ModelNotConfiguredError
    except ImportError:
        from model_gateway.embedding import embed
        from model_gateway.llm import ModelNotConfiguredError
    try:
        query_vectors = embed([query.strip()])
    except ModelNotConfiguredError:
        logger.debug("Embedding 未配置，FAQ 检索返回空")
        return []
    if not query_vectors or not query_vectors[0]:
        return []
    if not get_client():
        return []
    top_k = max(1, min(top_k, 20))
    results = search_with_filter(
        query_vectors=[query_vectors[0]],
        filter_expr=None,
        top_k=top_k,
        output_fields=[FIELD_DOC_ID, FIELD_CHUNK_TEXT],
        collection_name=FAQ_COLLECTION_NAME,
    )
    if not results or not results[0]:
        return []
    faq_ids = []
    for h in results[0]:
        entity = h.get("entity") or h
        doc_id = (entity.get(FIELD_DOC_ID) or "").strip()
        if doc_id.isdigit():
            faq_ids.append(int(doc_id))
    if not faq_ids:
        return []
    return get_faq_by_ids(faq_ids)
