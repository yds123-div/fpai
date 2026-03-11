"""
FAQ 同步：MySQL（结构化）→ Embedding → Milvus（向量库）。

与 faq_design.md 一致：仅同步在生效期内的 FAQ；全量替换（先按 source=faq 删除再插入）。
"""
from __future__ import annotations

import time

from pkg.logger import get_logger
from pkg.milvus_client import (
    get_client,
    ensure_collection,
    insert_chunks,
    delete_by_filter,
    FAQ_COLLECTION_NAME,
    FIELD_DOC_ID,
    FIELD_SOURCE,
    FIELD_CHUNK_TEXT,
)

from agents.faq.store import list_effective_faq

logger = get_logger(__name__)

SOURCE_FAQ = "faq"


def sync_faq_to_milvus() -> bool:
    """
    将 MySQL 中生效期内的 FAQ 同步到 Milvus：对 question 做 Embedding，写入 fpai_faq。
    先删除该 collection 内 source=faq 的旧数据，再全量插入。
    """
    try:
        from model_gateway import embed, ModelNotConfiguredError
    except ImportError:
        from model_gateway.embedding import embed
        from model_gateway.llm import ModelNotConfiguredError
    faq_list = list_effective_faq()
    if not faq_list:
        logger.info("无生效中 FAQ，同步跳过")
        return True
    try:
        questions = [q for _, q, _, _ in faq_list]
        vectors = embed(questions)
    except ModelNotConfiguredError:
        logger.warning("Embedding 未配置，FAQ 同步跳过")
        return False
    if not vectors or len(vectors) != len(faq_list):
        logger.warning("Embedding 结果与 FAQ 数量不一致")
        return False
    client = get_client()
    if not client:
        logger.warning("Milvus 未连接，FAQ 同步跳过")
        return False
    dim = len(vectors[0])
    if not ensure_collection(dim, collection_name=FAQ_COLLECTION_NAME):
        logger.warning("无法确保 FAQ collection 存在")
        return False
    delete_by_filter(FAQ_COLLECTION_NAME, f'{FIELD_SOURCE} == "{SOURCE_FAQ}"')
    now_ts = int(time.time())
    ids = [f"faq_{fid}" for fid, _, _, _ in faq_list]
    doc_ids = [str(fid) for fid, _, _, _ in faq_list]
    sources = [SOURCE_FAQ] * len(faq_list)
    permission_tags = [""] * len(faq_list)
    created_ats = [now_ts] * len(faq_list)
    chunk_texts = [q for _, q, _, _ in faq_list]
    ok = insert_chunks(
        ids=ids,
        vectors=vectors,
        doc_ids=doc_ids,
        sources=sources,
        permission_tags=permission_tags,
        created_ats=created_ats,
        chunk_texts=chunk_texts,
        collection_name=FAQ_COLLECTION_NAME,
    )
    if ok:
        logger.info("FAQ 同步完成，共 %d 条", len(faq_list))
    return ok
