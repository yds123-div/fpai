from __future__ import annotations

"""
Skill 配置存储（MySQL）：

- 用于 Skill 管理台：展示/导入/删除/启用禁用
- MVP：导入仅支持“注册一个 Python 模块路径”，运行时动态 import 并调用其中的 run(question, ctx)
"""

import importlib
import time
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skill_profiles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  skill_key VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  type VARCHAR(32) NOT NULL DEFAULT 'builtin',        -- builtin | custom
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  module_path VARCHAR(255) NOT NULL DEFAULT '',
  description VARCHAR(255) NOT NULL DEFAULT '',
  created_by VARCHAR(64) NOT NULL DEFAULT '',
  updated_by VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_skill_profiles_key (skill_key),
  KEY idx_skill_profiles_type (type),
  KEY idx_skill_profiles_enabled (enabled),
  KEY idx_skill_profiles_deleted_at (deleted_at),
  KEY idx_skill_profiles_updated_at (updated_at)
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
        logger.warning("ensure skill_profiles table failed: %s", e)
        return False


# ---- 轻量缓存：避免每次运行都查库（只用于读取） ----
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


def _cache_invalidate(skill_key: str | None = None) -> None:
    if not skill_key:
        _cache.clear()
        return
    _cache.pop(str(skill_key), None)


def _validate_module(module_path: str) -> bool:
    mp = (module_path or "").strip()
    if not mp:
        return False
    try:
        mod = importlib.import_module(mp)
    except Exception:
        return False
    fn = getattr(mod, "run", None)
    return callable(fn)


def _seed_builtin_skills() -> None:
    """
    预置当前代码内置 skills。
    - 不存在则插入
    - 已存在但 module_path 为空时补齐（不覆盖管理员修改）
    """
    if not _ensure_table():
        return
    seeds = [
        {
            "skill_key": "product_query",
            "name": "产品查询取数",
            "type": "builtin",
            "enabled": 1,
            "module_path": "agents.skills.product_query.runtime",
            "description": "榜单/筛选/基金列表等取数聚合",
        },
        {
            "skill_key": "product_compare",
            "name": "产品对比取数",
            "type": "builtin",
            "enabled": 1,
            "module_path": "agents.skills.product_compare.runtime",
            "description": "AkShare 聚合基金对比数据（支持上下文回填基金代码）",
        },
        {
            "skill_key": "product_interpret",
            "name": "产品解析取数",
            "type": "builtin",
            "enabled": 1,
            "module_path": "agents.skills.product_interpret.runtime",
            "description": "AkShare 聚合单只基金深度解读数据（基本信息/业绩/分析/盈亏概率/持仓明细/详情）",
        },
        {
            "skill_key": "product_recommend",
            "name": "产品推荐取数",
            "type": "builtin",
            "enabled": 1,
            "module_path": "agents.skills.product_recommend.runtime",
            "description": "根据客户画像偏好（低风险/稳健、理财/债券/少量混合等）筛选候选产品并输出推荐候选数据",
        },
        {
            "skill_key": "fund_name_to_code",
            "name": "基金名称转代码",
            "type": "builtin",
            "enabled": 1,
            "module_path": "agents.skills.fund_name_to_code.runtime",
            "description": "根据基金名称查询基金代码，支持模糊匹配",
        },
    ]
    try:
        with get_connection() as conn:
            if not conn:
                return
            with conn.cursor() as cur:
                for s in seeds:
                    cur.execute(
                        """
                        INSERT IGNORE INTO skill_profiles (skill_key, name, type, enabled, module_path, description, created_by, updated_by, deleted_at)
                        VALUES (%s,%s,%s,%s,%s,%s,'','',NULL)
                        """,
                        (
                            s["skill_key"],
                            s["name"],
                            s["type"],
                            int(s["enabled"]),
                            s["module_path"],
                            s.get("description") or "",
                        ),
                    )
                    cur.execute(
                        """
                        UPDATE skill_profiles
                        SET
                          name = CASE WHEN (name IS NULL OR name='') THEN %s ELSE name END,
                          type = CASE WHEN (type IS NULL OR type='') THEN %s ELSE type END,
                          enabled = CASE WHEN enabled IS NULL THEN %s ELSE enabled END,
                          module_path = CASE WHEN (module_path IS NULL OR module_path='') THEN %s ELSE module_path END,
                          description = CASE WHEN (description IS NULL OR description='') THEN %s ELSE description END
                        WHERE skill_key=%s AND deleted_at IS NULL
                        """,
                        (
                            s["name"],
                            s["type"],
                            int(s["enabled"]),
                            s["module_path"],
                            s.get("description") or "",
                            s["skill_key"],
                        ),
                    )
            conn.commit()
    except Exception as e:
        logger.warning("seed builtin skills failed: %s", e)


def list_skills(include_deleted: bool = False) -> list[dict[str, Any]]:
    if not _ensure_table():
        return []
    _seed_builtin_skills()
    where = "" if include_deleted else "WHERE deleted_at IS NULL"
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT skill_key, name, type, enabled, module_path, description, updated_by, updated_at, deleted_at
                    FROM skill_profiles
                    {where}
                    ORDER BY updated_at DESC
                    """
                )
                rows = cur.fetchall() or []
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "skill_key": r[0] or "",
                    "name": r[1] or "",
                    "type": r[2] or "custom",
                    "enabled": int(r[3] or 0),
                    "module_path": r[4] or "",
                    "description": r[5] or "",
                    "updated_by": r[6] or "",
                    "updated_at": str(r[7]) if r[7] is not None else None,
                    "deleted_at": str(r[8]) if r[8] is not None else None,
                }
            )
        return out
    except Exception as e:
        logger.warning("list_skills failed: %s", e)
        return []


def get_skill(skill_key: str) -> dict[str, Any] | None:
    k = (skill_key or "").strip()
    if not k:
        return None
    cached = _cache_get(k)
    if cached is not None:
        return cached
    if not _ensure_table():
        return None
    _seed_builtin_skills()
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT skill_key, name, type, enabled, module_path, description, updated_by, updated_at, deleted_at
                    FROM skill_profiles
                    WHERE skill_key=%s
                    LIMIT 1
                    """,
                    (k,),
                )
                r = cur.fetchone()
        if not r:
            return None
        obj = {
            "skill_key": r[0] or "",
            "name": r[1] or "",
            "type": r[2] or "custom",
            "enabled": int(r[3] or 0),
            "module_path": r[4] or "",
            "description": r[5] or "",
            "updated_by": r[6] or "",
            "updated_at": str(r[7]) if r[7] is not None else None,
            "deleted_at": str(r[8]) if r[8] is not None else None,
        }
        _cache_set(k, obj)
        return obj
    except Exception as e:
        logger.warning("get_skill failed: %s", e)
        return None


def upsert_skill(payload: dict[str, Any], *, actor_user_id: str) -> bool:
    if not _ensure_table():
        return False
    _seed_builtin_skills()
    key = (payload.get("skill_key") or "").strip()
    name = (payload.get("name") or "").strip()
    typ = (payload.get("type") or "custom").strip() or "custom"
    enabled = 1 if int(payload.get("enabled", 1) or 1) else 0
    module_path = (payload.get("module_path") or "").strip()
    desc = (payload.get("description") or "").strip()
    if not key or not name:
        return False
    if typ not in ("builtin", "custom"):
        typ = "custom"
    # 安全：必须是可 import 且含 run()
    if not _validate_module(module_path):
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skill_profiles (skill_key, name, type, enabled, module_path, description, created_by, updated_by, deleted_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NULL)
                    ON DUPLICATE KEY UPDATE
                      name=VALUES(name),
                      type=VALUES(type),
                      enabled=VALUES(enabled),
                      module_path=VALUES(module_path),
                      description=VALUES(description),
                      updated_by=VALUES(updated_by),
                      deleted_at=NULL
                    """,
                    (key, name, typ, enabled, module_path, desc, actor_user_id or "", actor_user_id or ""),
                )
            conn.commit()
        _cache_invalidate(key)
        return True
    except Exception as e:
        logger.warning("upsert_skill failed: %s", e)
        return False


def soft_delete_skill(skill_key: str, *, actor_user_id: str) -> bool:
    if not _ensure_table():
        return False
    k = (skill_key or "").strip()
    if not k:
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE skill_profiles
                    SET deleted_at = NOW(), updated_by=%s
                    WHERE skill_key=%s AND deleted_at IS NULL
                    """,
                    (actor_user_id or "", k),
                )
            conn.commit()
            ok = (cur.rowcount or 0) > 0
        _cache_invalidate(k)
        return ok
    except Exception as e:
        logger.warning("soft_delete_skill failed: %s", e)
        return False

