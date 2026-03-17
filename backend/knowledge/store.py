# -*- coding: utf-8 -*-
"""
知识库（外部知识库系统）映射表：

- 将“知识库名称 <-> UUID”映射存到本地 MySQL，供前端下拉选择与检索调用使用。
- UUID 将用于外部检索接口的 knowledge_base_ids 参数。

本模块只负责本地表的 CRUD 与 upsert。
"""

from __future__ import annotations

from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
  uuid VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (uuid),
  KEY idx_kb_enabled (enabled),
  KEY idx_kb_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def _ensure_table() -> bool:
    if not mysql_configured():
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(TABLE_SQL)
            conn.commit()
        return True
    except Exception as e:
        logger.warning("ensure knowledge_bases table failed: %s", e)
        return False


def list_knowledge_bases(enabled_only: bool = True) -> list[dict[str, Any]]:
    """返回知识库列表（uuid、name）。"""
    if not _ensure_table():
        return []
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                if enabled_only:
                    cur.execute(
                        "SELECT uuid, name, enabled, updated_at FROM knowledge_bases WHERE enabled = 1 ORDER BY name"
                    )
                else:
                    cur.execute("SELECT uuid, name, enabled, updated_at FROM knowledge_bases ORDER BY name")
                rows = cur.fetchall() or []
        return [
            {
                "uuid": (r[0] or "").strip(),
                "name": r[1] or "",
                "enabled": int(r[2] or 0),
                "updated_at": str(r[3]) if r[3] is not None else None,
            }
            for r in rows
            if r and (r[0] or "").strip()
        ]
    except Exception as e:
        logger.warning("list_knowledge_bases failed: %s", e)
        return []


def upsert_knowledge_bases(items: list[dict[str, Any]]) -> int:
    """
    批量 upsert（按 uuid）。
    items: [{uuid, name, enabled?}]
    返回写入/更新条数（rowcount 可能受驱动影响，仅做参考）。
    """
    if not items or not _ensure_table():
        return 0
    normalized: list[tuple[str, str, int]] = []
    for it in items:
        uuid = (it.get("uuid") or it.get("id") or it.get("knowledge_base_id") or "").strip()
        name = (it.get("name") or it.get("title") or "").strip()
        if not uuid or not name:
            continue
        enabled = 1 if int(it.get("enabled", 1) or 1) else 0
        normalized.append((uuid, name, enabled))
    if not normalized:
        return 0
    try:
        with get_connection() as conn:
            if not conn:
                return 0
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO knowledge_bases (uuid, name, enabled)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      name = VALUES(name),
                      enabled = VALUES(enabled)
                    """,
                    normalized,
                )
                conn.commit()
                return int(cur.rowcount or 0)
    except Exception as e:
        logger.warning("upsert_knowledge_bases failed: %s", e)
        return 0

