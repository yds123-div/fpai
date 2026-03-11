"""
FAQ 数据层：MySQL 结构化存储（入库）、按 id 批量查询（供检索层回表取 answer）。

与 faq_design.md 一致：FAQ 入库 → MySQL；同步与检索见 sync.py / retrieval 层。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)

# 生效期 SQL 条件：当前时间在 [effective_from, effective_to] 内或两者均为 NULL
EFFECTIVE_COND = (
    "(effective_from IS NULL AND effective_to IS NULL) OR "
    "(effective_from IS NOT NULL AND effective_to IS NOT NULL AND NOW() BETWEEN effective_from AND effective_to) OR "
    "(effective_from IS NULL AND effective_to IS NOT NULL AND NOW() <= effective_to) OR "
    "(effective_from IS NOT NULL AND effective_to IS NULL AND NOW() >= effective_from)"
)


@dataclass
class FAQHit:
    """单条 FAQ 命中。"""
    id: int
    question: str
    answer: str
    tags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "tags": self.tags,
        }


def list_effective_faq() -> list[tuple[int, str, str, Any]]:
    """
    列出所有在生效期内的 FAQ，用于同步到向量库。
    返回 [(id, question, answer, tags), ...]。
    """
    if not mysql_configured():
        return []
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, question, answer, tags FROM faq WHERE {EFFECTIVE_COND} ORDER BY id""",
                )
                rows = cur.fetchall()
            out = []
            for row in rows:
                tid, q, a, tags = row[0], row[1], row[2], row[3]
                out.append((int(tid), q or "", a or "", tags))
            return out
    except Exception as e:
        logger.exception("list_effective_faq 失败: %s", e)
        return []


def get_faq_by_ids(faq_ids: list[int]) -> list[FAQHit]:
    """按 id 列表从 MySQL 取完整 FAQ，供向量检索层回表。保持 id 顺序与传入一致（按传入顺序排序）。"""
    if not faq_ids or not mysql_configured():
        return []
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            placeholders = ",".join(["%s"] * len(faq_ids))
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, question, answer, tags FROM faq WHERE id IN ({placeholders}) AND ({EFFECTIVE_COND})""",
                    faq_ids,
                )
                rows = cur.fetchall()
            id_to_row = {}
            for row in rows:
                tid, q, a, tags = row[0], row[1], row[2], row[3]
                tag_list = None
                if tags is not None:
                    if isinstance(tags, list):
                        tag_list = tags
                    else:
                        try:
                            tag_list = json.loads(tags) if isinstance(tags, str) else None
                        except Exception:
                            pass
                id_to_row[int(tid)] = FAQHit(id=int(tid), question=q or "", answer=a or "", tags=tag_list)
            return [id_to_row[i] for i in faq_ids if i in id_to_row]
    except Exception as e:
        logger.exception("get_faq_by_ids 失败: %s", e)
        return []
