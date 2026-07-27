# -*- coding: utf-8 -*-
"""
模型配置存储（MySQL）：

- 支持本地 Ollama 与远程 OpenAI 兼容接口（Remote API）
- API Key 为敏感信息：后端不向前端回传明文，仅回传 has_api_key
"""

from __future__ import annotations

from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ai_models (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  source VARCHAR(32) NOT NULL,            -- ollama | remote
  vendor VARCHAR(64) NOT NULL DEFAULT '', -- custom/openai/...
  model_name VARCHAR(128) NOT NULL DEFAULT '',
  base_url VARCHAR(512) NOT NULL DEFAULT '',
  api_key VARCHAR(512) NOT NULL DEFAULT '',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ai_models_name (name),
  KEY idx_ai_models_enabled (enabled),
  KEY idx_ai_models_source (source)
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
        logger.warning("ensure ai_models table failed: %s", e)
        return False


def list_models(enabled_only: bool = True) -> list[dict[str, Any]]:
    if not _ensure_table():
        return []
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                if enabled_only:
                    cur.execute(
                        """
                        SELECT id, name, source, vendor, model_name, base_url, api_key, enabled, updated_at
                        FROM ai_models WHERE enabled = 1 ORDER BY updated_at DESC
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, name, source, vendor, model_name, base_url, api_key, enabled, updated_at
                        FROM ai_models ORDER BY updated_at DESC
                        """
                    )
                rows = cur.fetchall() or []
        out: list[dict[str, Any]] = []
        for r in rows:
            api_key = (r[6] or "").strip()
            display_name = (r[1] or "").strip() or (r[4] or "").strip()
            out.append(
                {
                    "id": int(r[0]),
                    "name": display_name,
                    "source": r[2] or "",
                    "vendor": r[3] or "",
                    "model_name": r[4] or "",
                    "base_url": r[5] or "",
                    "enabled": int(r[7] or 0),
                    "has_api_key": bool(api_key),
                    "updated_at": str(r[8]) if r[8] is not None else None,
                }
            )
        return out
    except Exception as e:
        logger.warning("list_models failed: %s", e)
        return []


def get_model_by_id(model_id: int) -> dict[str, Any] | None:
    if not _ensure_table():
        return None
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, source, vendor, model_name, base_url, api_key, enabled
                    FROM ai_models WHERE id = %s LIMIT 1
                    """,
                    (int(model_id),),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "name": row[1] or "",
            "source": row[2] or "",
            "vendor": row[3] or "",
            "model_name": row[4] or "",
            "base_url": row[5] or "",
            "api_key": row[6] or "",
            "enabled": int(row[7] or 0),
        }
    except Exception as e:
        logger.warning("get_model_by_id failed: %s", e)
        return None


def upsert_model(payload: dict[str, Any]) -> int | None:
    """
    新增/更新模型。若 payload 含 id 则更新，否则新增。
    返回 id，失败返回 None。
    """
    if not _ensure_table():
        return None
    model_id = payload.get("id")
    name = (payload.get("name") or "").strip()
    source = (payload.get("source") or "").strip()
    vendor = (payload.get("vendor") or "").strip()
    model_name = (payload.get("model_name") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    enabled = 1 if int(payload.get("enabled", 1) or 1) else 0
    # 前端仅保留 model_name；这里将 name 兜底为 model_name，兼容旧表结构
    if not name:
        name = model_name
    if not name or not model_name or source not in ("ollama", "remote"):
        return None
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                if model_id:
                    # api_key 允许不传（保持原值）
                    if api_key:
                        cur.execute(
                            """
                            UPDATE ai_models
                            SET name=%s, source=%s, vendor=%s, model_name=%s, base_url=%s, api_key=%s, enabled=%s
                            WHERE id=%s
                            """,
                            (name, source, vendor, model_name, base_url, api_key, enabled, int(model_id)),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE ai_models
                            SET name=%s, source=%s, vendor=%s, model_name=%s, base_url=%s, enabled=%s
                            WHERE id=%s
                            """,
                            (name, source, vendor, model_name, base_url, enabled, int(model_id)),
                        )
                    conn.commit()
                    return int(model_id)
                cur.execute(
                    """
                    INSERT INTO ai_models (name, source, vendor, model_name, base_url, api_key, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (name, source, vendor, model_name, base_url, api_key, enabled),
                )
                conn.commit()
                return int(cur.lastrowid)
    except Exception as e:
        logger.warning("upsert_model failed: %s", e)
        return None


def delete_model(model_id: int) -> bool:
    if not _ensure_table():
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ai_models WHERE id = %s", (int(model_id),))
                conn.commit()
                return (cur.rowcount or 0) > 0
    except Exception as e:
        logger.warning("delete_model failed: %s", e)
        return False

