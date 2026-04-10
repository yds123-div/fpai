from __future__ import annotations

"""
Agent 配置存储（MySQL）：

- 用于 Agent 管理台：展示/编辑提示词(system_prompt)、模型选择(model_id)、启用/禁用等
- MVP：custom agent 仅用于管理，不参与对话路由；内置 agent 支持配置覆盖
"""

import time
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured


logger = get_logger(__name__)


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_profiles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agent_key VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  type VARCHAR(32) NOT NULL DEFAULT 'custom',        -- builtin | custom
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  system_prompt LONGTEXT,
  skill_keys LONGTEXT,
  model_id BIGINT UNSIGNED NULL,
  created_by VARCHAR(64) NOT NULL DEFAULT '',
  updated_by VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_agent_profiles_key (agent_key),
  KEY idx_agent_profiles_type (type),
  KEY idx_agent_profiles_enabled (enabled),
  KEY idx_agent_profiles_deleted_at (deleted_at),
  KEY idx_agent_profiles_updated_at (updated_at)
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
                # 兼容老表：补列（若已存在会失败，忽略即可）
                try:
                    cur.execute("ALTER TABLE agent_profiles ADD COLUMN skill_keys LONGTEXT")
                except Exception:
                    pass
            conn.commit()
        return True
    except Exception as e:
        logger.warning("ensure agent_profiles table failed: %s", e)
        return False


def _seed_builtin_agents() -> None:
    """
    将当前代码内置的业务 agent 预置到 agent_profiles，便于“Agent 管理”页面直接编辑。
    - 若记录不存在则创建
    - 若记录已存在则不覆盖（避免覆盖管理员在页面里的修改）
    """
    if not _ensure_table():
        return
    try:
        from agents.fund_agent.product_query.agent import DEFAULT_SYSTEM_PROMPT as PQ_PROMPT
        from agents.fund_agent.product_interpret.agent import DEFAULT_SYSTEM_PROMPT as PI_PROMPT
        from agents.fund_agent.product_compare.agent import DEFAULT_SYSTEM_PROMPT as PC_PROMPT
        from agents.fund_agent.product_recommend.agent import DEFAULT_SYSTEM_PROMPT as PR_PROMPT
        from agents.fund_agent.other.agent import DEFAULT_SYSTEM_PROMPT as O_PROMPT
        from agents.fund_agent_framework import COORDINATOR_DEFAULT_SYSTEM_PROMPT
    except Exception:
        return

    seeds = [
        {
            "agent_key": "product_query",
            "name": "产品查询",
            "type": "builtin",
            "enabled": 1,
            "system_prompt": PQ_PROMPT or "",
            "skill_keys": '["product_query","product_compare"]',
            "model_id": None,
        },
        {
            "agent_key": "product_interpret",
            "name": "产品解析",
            "type": "builtin",
            "enabled": 1,
            "system_prompt": PI_PROMPT or "",
            "skill_keys": '["product_compare"]',
            "model_id": None,
        },
        {
            "agent_key": "product_compare",
            "name": "产品对比",
            "type": "builtin",
            "enabled": 1,
            "system_prompt": PC_PROMPT or "",
            "skill_keys": '["product_compare"]',
            "model_id": None,
        },
        {
            "agent_key": "product_recommend",
            "name": "产品推荐",
            "type": "builtin",
            "enabled": 1,
            "system_prompt": PR_PROMPT or "",
            "skill_keys": '["product_recommend"]',
            "model_id": None,
        },
        {
            "agent_key": "task_planner",
            "name": "任务规划",
            "type": "builtin",
            "enabled": 1,
            "system_prompt": COORDINATOR_DEFAULT_SYSTEM_PROMPT or "",
            "skill_keys": "[]",
            "model_id": None,
        },
        {"agent_key": "other", "name": "其它问答", "type": "builtin", "enabled": 1, "system_prompt": O_PROMPT or "", "skill_keys": "[]", "model_id": None},
    ]
    try:
        with get_connection() as conn:
            if not conn:
                return
            with conn.cursor() as cur:
                for s in seeds:
                    # 1) 不存在则插入
                    cur.execute(
                        """
                        INSERT IGNORE INTO agent_profiles (agent_key, name, type, enabled, system_prompt, skill_keys, model_id, created_by, updated_by, deleted_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', NULL)
                        """,
                        (
                            s["agent_key"],
                            s["name"],
                            s["type"],
                            int(s["enabled"]),
                            s.get("system_prompt") or "",
                            s.get("skill_keys") or "[]",
                            s.get("model_id"),
                        ),
                    )
                    # 2) 已存在但 prompt 为空时，补齐默认 prompt（不覆盖管理员已编辑的内容）
                    cur.execute(
                        """
                        UPDATE agent_profiles
                        SET
                          name = CASE WHEN (name IS NULL OR name='') THEN %s ELSE name END,
                          type = CASE WHEN (type IS NULL OR type='') THEN %s ELSE type END,
                          enabled = CASE WHEN enabled IS NULL THEN %s ELSE enabled END,
                          system_prompt = CASE WHEN (system_prompt IS NULL OR system_prompt='') THEN %s ELSE system_prompt END,
                          skill_keys = CASE WHEN (skill_keys IS NULL OR skill_keys='') THEN %s ELSE skill_keys END
                        WHERE agent_key=%s AND deleted_at IS NULL
                        """,
                        (
                            s["name"],
                            s["type"],
                            int(s["enabled"]),
                            s.get("system_prompt") or "",
                            s.get("skill_keys") or "[]",
                            s["agent_key"],
                        ),
                    )
                    # product_recommend：为了避免历史 seed 错误（例如写成 product_query/product_compare）
                    # 在旧记录 skill_keys 非空时无法被上面的 CASE 更新，这里做一次定向兜底修正。
                    if s.get("agent_key") == "product_recommend":
                        cur.execute(
                            """
                            UPDATE agent_profiles
                            SET skill_keys=%s
                            WHERE agent_key=%s AND deleted_at IS NULL
                              AND (skill_keys IS NULL OR skill_keys='' OR skill_keys LIKE '%product_query%')
                            """,
                            (s.get("skill_keys") or "[]", s["agent_key"]),
                        )
            conn.commit()
    except Exception as e:
        logger.warning("seed builtin agents failed: %s", str(e))


# ---- 轻量缓存：避免每次 run 都查库（仅用于读取） ----
_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(key: str) -> dict[str, Any] | None:
    item = _cache.get(key)
    if not item:
        return None
    ts, obj = item
    if (time.time() - ts) > _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return obj


def _cache_set(key: str, obj: dict[str, Any]) -> None:
    _cache[key] = (time.time(), obj)


def _cache_invalidate(agent_key: str | None = None) -> None:
    if not agent_key:
        _cache.clear()
        return
    _cache.pop(str(agent_key), None)


def list_agents(include_deleted: bool = False) -> list[dict[str, Any]]:
    if not _ensure_table():
        return []
    _seed_builtin_agents()
    where = "" if include_deleted else "WHERE deleted_at IS NULL"
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT agent_key, name, type, enabled, system_prompt, skill_keys, model_id, updated_by, updated_at, deleted_at
                    FROM agent_profiles
                    {where}
                    ORDER BY updated_at DESC
                    """
                )
                rows = cur.fetchall() or []
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "agent_key": r[0] or "",
                    "name": r[1] or "",
                    "type": r[2] or "custom",
                    "enabled": int(r[3] or 0),
                    "system_prompt": r[4] or "",
                    "skill_keys": r[5] or "",
                    "model_id": int(r[6]) if r[6] is not None else None,
                    "updated_by": r[7] or "",
                    "updated_at": str(r[8]) if r[8] is not None else None,
                    "deleted_at": str(r[9]) if r[9] is not None else None,
                }
            )
        return out
    except Exception as e:
        logger.warning("list_agents failed: %s", e)
        return []


def get_agent(agent_key: str) -> dict[str, Any] | None:
    agent_key = (agent_key or "").strip()
    if not agent_key:
        return None
    cached = _cache_get(agent_key)
    if cached is not None:
        return cached
    if not _ensure_table():
        return None
    _seed_builtin_agents()
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_key, name, type, enabled, system_prompt, skill_keys, model_id, updated_by, updated_at, deleted_at
                    FROM agent_profiles
                    WHERE agent_key = %s
                    LIMIT 1
                    """,
                    (agent_key,),
                )
                r = cur.fetchone()
        if not r:
            return None
        obj = {
            "agent_key": r[0] or "",
            "name": r[1] or "",
            "type": r[2] or "custom",
            "enabled": int(r[3] or 0),
            "system_prompt": r[4] or "",
            "skill_keys": r[5] or "",
            "model_id": int(r[6]) if r[6] is not None else None,
            "updated_by": r[7] or "",
            "updated_at": str(r[8]) if r[8] is not None else None,
            "deleted_at": str(r[9]) if r[9] is not None else None,
        }
        _cache_set(agent_key, obj)
        return obj
    except Exception as e:
        logger.warning("get_agent failed: %s", e)
        return None


def upsert_agent(payload: dict[str, Any], *, actor_user_id: str) -> bool:
    """
    新增/更新 agent_profile（按 agent_key upsert）。
    """
    if not _ensure_table():
        return False
    agent_key = (payload.get("agent_key") or "").strip()
    name = (payload.get("name") or "").strip()
    typ = (payload.get("type") or "custom").strip() or "custom"
    enabled = 1 if int(payload.get("enabled", 1) or 1) else 0
    system_prompt = payload.get("system_prompt")
    skill_keys = payload.get("skill_keys")
    model_id = payload.get("model_id")

    if not agent_key:
        return False
    if typ not in ("builtin", "custom"):
        typ = "custom"

    # model_id 可空
    mid: int | None = None
    try:
        if model_id is not None and str(model_id).strip() != "":
            mid = int(model_id)
    except Exception:
        mid = None

    try:
        sk_json = ""
        if skill_keys is None:
            sk_json = ""
        elif isinstance(skill_keys, str):
            sk_json = skill_keys
        elif isinstance(skill_keys, list):
            try:
                import json as _json

                sk_json = _json.dumps(skill_keys, ensure_ascii=False)
            except Exception:
                sk_json = ""
        else:
            sk_json = ""

        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_profiles (agent_key, name, type, enabled, system_prompt, skill_keys, model_id, created_by, updated_by, deleted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                    ON DUPLICATE KEY UPDATE
                      name=VALUES(name),
                      type=VALUES(type),
                      enabled=VALUES(enabled),
                      system_prompt=VALUES(system_prompt),
                      skill_keys=VALUES(skill_keys),
                      model_id=VALUES(model_id),
                      updated_by=VALUES(updated_by),
                      deleted_at=NULL
                    """,
                    (
                        agent_key,
                        name,
                        typ,
                        enabled,
                        system_prompt if system_prompt is not None else "",
                        sk_json,
                        mid,
                        actor_user_id or "",
                        actor_user_id or "",
                    ),
                )
            conn.commit()
        _cache_invalidate(agent_key)
        return True
    except Exception as e:
        logger.warning("upsert_agent failed: %s", e)
        return False


def soft_delete_agent(agent_key: str, *, actor_user_id: str) -> bool:
    if not _ensure_table():
        return False
    agent_key = (agent_key or "").strip()
    if not agent_key:
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_profiles
                    SET deleted_at = NOW(), updated_by=%s
                    WHERE agent_key=%s AND deleted_at IS NULL
                    """,
                    (actor_user_id or "", agent_key),
                )
            conn.commit()
            ok = (cur.rowcount or 0) > 0
        _cache_invalidate(agent_key)
        return ok
    except Exception as e:
        logger.warning("soft_delete_agent failed: %s", e)
        return False

