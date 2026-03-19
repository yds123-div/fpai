from __future__ import annotations

"""
RBAC（角色/菜单/关联）存储（MySQL）：

- roles：角色
- menus：菜单（支持树形 parent_id）
- user_roles：用户-角色
- role_menus：角色-菜单

约定：
- 普通用户：默认无角色，仅能看到主界面（前端硬编码主界面菜单，不依赖本接口）
- 管理员：admin 角色拥有所有后台菜单权限
"""

import time
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS roles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  description VARCHAR(255) NOT NULL DEFAULT '',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_roles_code (code),
  KEY idx_roles_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS menus (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  path VARCHAR(255) NOT NULL DEFAULT '',
  icon VARCHAR(64) NOT NULL DEFAULT '',
  parent_id BIGINT UNSIGNED NULL,
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_menus_code (code),
  KEY idx_menus_parent (parent_id),
  KEY idx_menus_enabled (enabled),
  KEY idx_menus_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_roles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id VARCHAR(64) NOT NULL,
  role_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_roles (user_id, role_id),
  KEY idx_user_roles_user (user_id),
  KEY idx_user_roles_role (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_menus (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  role_id BIGINT UNSIGNED NOT NULL,
  menu_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_role_menus (role_id, menu_id),
  KEY idx_role_menus_role (role_id),
  KEY idx_role_menus_menu (menu_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def _ensure_tables() -> bool:
    if not mysql_configured():
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                for stmt in [s.strip() for s in TABLE_SQL.split(";") if s.strip()]:
                    cur.execute(stmt)
            conn.commit()
        return True
    except Exception as e:
        logger.warning("ensure rbac tables failed: %s", e)
        return False


# ---- 轻量缓存：角色判断经常被中间件调用 ----
_CACHE_TTL_SECONDS = 15.0
_role_cache: dict[str, tuple[float, list[str]]] = {}


def _cache_get_roles(user_id: str) -> list[str] | None:
    item = _role_cache.get(user_id)
    if not item:
        return None
    ts, roles = item
    if (time.time() - ts) > _CACHE_TTL_SECONDS:
        _role_cache.pop(user_id, None)
        return None
    return roles


def _cache_set_roles(user_id: str, roles: list[str]) -> None:
    _role_cache[user_id] = (time.time(), roles)


def invalidate_user_roles_cache(user_id: str | None = None) -> None:
    if not user_id:
        _role_cache.clear()
        return
    _role_cache.pop(str(user_id), None)


def ensure_seed_admin() -> None:
    """
    确保：
    - roles 中存在 admin
    - menus 中存在默认后台菜单项（用户/参数/模型/知识库/Agent/角色/菜单）
    - admin 角色绑定所有后台菜单
    - account='admin' 的用户被赋予 admin 角色（若该用户存在）
    """
    if not _ensure_tables():
        return
    try:
        with get_connection() as conn:
            if not conn:
                return
            with conn.cursor() as cur:
                # role: admin
                cur.execute("SELECT id FROM roles WHERE code=%s LIMIT 1", ("admin",))
                row = cur.fetchone()
                if row:
                    admin_role_id = int(row[0])
                else:
                    cur.execute(
                        "INSERT INTO roles(code,name,description,enabled) VALUES(%s,%s,%s,1)",
                        ("admin", "管理员", "系统管理员（拥有全部菜单权限）"),
                    )
                    admin_role_id = int(cur.lastrowid or 0)

                # default menus（后台）
                default_menus = [
                    ("admin-user", "用户管理", "/admin/system/user", "user", 10),
                    ("admin-roles", "角色管理", "/admin/system/roles", "team", 11),
                    ("admin-menus", "菜单管理", "/admin/system/menus", "appstore", 12),
                    ("admin-params", "参数管理", "/admin/system/config", "setting", 20),
                    ("admin-model", "模型管理", "/admin/model", "thunderbolt", 30),
                    ("admin-knowledge", "知识库", "/admin/knowledge", "database", 40),
                    ("admin-agent", "Agent管理", "/admin/agent", "tool", 50),
                    ("admin-skill", "Skill管理", "/admin/skill", "tool", 51),
                    ("theme-settings", "主题样式设置", "/admin/theme-settings", "setting", 55),
                ]
                menu_ids: list[int] = []
                for code, name, path, icon, order in default_menus:
                    cur.execute("SELECT id FROM menus WHERE code=%s LIMIT 1", (code,))
                    r = cur.fetchone()
                    if r:
                        mid = int(r[0])
                        # 更新路径/名称/图标/排序，保证一致
                        cur.execute(
                            "UPDATE menus SET name=%s, path=%s, icon=%s, sort_order=%s, enabled=1 WHERE id=%s",
                            (name, path, icon, int(order), mid),
                        )
                    else:
                        cur.execute(
                            "INSERT INTO menus(code,name,path,icon,parent_id,sort_order,enabled) VALUES(%s,%s,%s,%s,NULL,%s,1)",
                            (code, name, path, icon, int(order)),
                        )
                        mid = int(cur.lastrowid or 0)
                    menu_ids.append(mid)

                # admin role bind all menus
                for mid in menu_ids:
                    cur.execute(
                        "INSERT IGNORE INTO role_menus(role_id, menu_id) VALUES(%s,%s)",
                        (admin_role_id, mid),
                    )

                # attach admin role to account=admin if exists
                cur.execute("SELECT id FROM users WHERE account=%s LIMIT 1", ("admin",))
                u = cur.fetchone()
                if u:
                    uid = str(u[0])
                    cur.execute(
                        "INSERT IGNORE INTO user_roles(user_id, role_id) VALUES(%s,%s)",
                        (uid, admin_role_id),
                    )
                    invalidate_user_roles_cache(uid)
            conn.commit()
    except Exception as e:
        logger.warning("ensure_seed_admin failed: %s", e)


def list_roles() -> list[dict[str, Any]]:
    if not _ensure_tables():
        return []
    ensure_seed_admin()
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute("SELECT id, code, name, description, enabled, updated_at FROM roles ORDER BY id ASC")
                rows = cur.fetchall() or []
        return [
            {
                "id": int(r[0]),
                "code": r[1] or "",
                "name": r[2] or "",
                "description": r[3] or "",
                "enabled": int(r[4] or 0),
                "updated_at": str(r[5]) if r[5] is not None else None,
            }
            for r in rows
        ]
    except Exception:
        return []


def upsert_role(payload: dict[str, Any]) -> bool:
    if not _ensure_tables():
        return False
    ensure_seed_admin()
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        return False
    desc = (payload.get("description") or "").strip()
    enabled = 1 if bool(payload.get("enabled", True)) else 0
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM roles WHERE code=%s LIMIT 1", (code,))
                row = cur.fetchone()
                if row:
                    rid = int(row[0])
                    cur.execute(
                        "UPDATE roles SET name=%s, description=%s, enabled=%s WHERE id=%s",
                        (name, desc, enabled, rid),
                    )
                else:
                    cur.execute(
                        "INSERT INTO roles(code,name,description,enabled) VALUES(%s,%s,%s,%s)",
                        (code, name, desc, enabled),
                    )
            conn.commit()
        return True
    except Exception:
        return False


def list_menus() -> list[dict[str, Any]]:
    if not _ensure_tables():
        return []
    ensure_seed_admin()
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, code, name, path, icon, parent_id, sort_order, enabled, updated_at FROM menus ORDER BY sort_order ASC, id ASC"
                )
                rows = cur.fetchall() or []
        return [
            {
                "id": int(r[0]),
                "code": r[1] or "",
                "name": r[2] or "",
                "path": r[3] or "",
                "icon": r[4] or "",
                "parent_id": int(r[5]) if r[5] is not None else None,
                "sort_order": int(r[6] or 0),
                "enabled": int(r[7] or 0),
                "updated_at": str(r[8]) if r[8] is not None else None,
            }
            for r in rows
        ]
    except Exception:
        return []


def upsert_menu(payload: dict[str, Any]) -> bool:
    if not _ensure_tables():
        return False
    ensure_seed_admin()
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    path = (payload.get("path") or "").strip()
    if not code or not name:
        return False
    icon = (payload.get("icon") or "").strip()
    parent_id = payload.get("parent_id")
    sort_order = int(payload.get("sort_order") or 0)
    enabled = 1 if bool(payload.get("enabled", True)) else 0
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM menus WHERE code=%s LIMIT 1", (code,))
                row = cur.fetchone()
                if row:
                    mid = int(row[0])
                    cur.execute(
                        "UPDATE menus SET name=%s, path=%s, icon=%s, parent_id=%s, sort_order=%s, enabled=%s WHERE id=%s",
                        (name, path, icon, parent_id, sort_order, enabled, mid),
                    )
                else:
                    cur.execute(
                        "INSERT INTO menus(code,name,path,icon,parent_id,sort_order,enabled) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (code, name, path, icon, parent_id, sort_order, enabled),
                    )
            conn.commit()
        return True
    except Exception:
        return False


def get_user_role_codes(user_id: str) -> list[str]:
    uid = (user_id or "").strip()
    if not uid or not _ensure_tables():
        return []
    cached = _cache_get_roles(uid)
    if cached is not None:
        return cached
    ensure_seed_admin()
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.code
                    FROM user_roles ur
                    JOIN roles r ON r.id = ur.role_id
                    WHERE ur.user_id=%s AND r.enabled=1
                    """,
                    (uid,),
                )
                rows = cur.fetchall() or []
        roles = [str(r[0]) for r in rows if r and r[0]]
        _cache_set_roles(uid, roles)
        return roles
    except Exception:
        return []


def set_user_roles(user_id: str, role_codes: list[str]) -> bool:
    uid = (user_id or "").strip()
    if not uid or not _ensure_tables():
        return False
    ensure_seed_admin()
    codes = [c.strip() for c in (role_codes or []) if (c or "").strip()]
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_roles WHERE user_id=%s", (uid,))
                if codes:
                    cur.execute("SELECT id, code FROM roles WHERE code IN %s", (tuple(codes),))
                    rows = cur.fetchall() or []
                    id_by_code = {str(r[1]): int(r[0]) for r in rows}
                    for code in codes:
                        rid = id_by_code.get(code)
                        if rid:
                            cur.execute(
                                "INSERT IGNORE INTO user_roles(user_id, role_id) VALUES(%s,%s)",
                                (uid, rid),
                            )
            conn.commit()
        invalidate_user_roles_cache(uid)
        return True
    except Exception:
        return False


def get_user_roles(user_id: str) -> list[str]:
    """返回用户已分配的角色 code 列表（包含禁用角色也会过滤掉）。"""
    return get_user_role_codes(user_id)


def set_role_menus(role_code: str, menu_codes: list[str]) -> bool:
    rc = (role_code or "").strip()
    if not rc or not _ensure_tables():
        return False
    ensure_seed_admin()
    codes = [c.strip() for c in (menu_codes or []) if (c or "").strip()]
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM roles WHERE code=%s LIMIT 1", (rc,))
                rr = cur.fetchone()
                if not rr:
                    return False
                rid = int(rr[0])
                cur.execute("DELETE FROM role_menus WHERE role_id=%s", (rid,))
                if codes:
                    cur.execute("SELECT id, code FROM menus WHERE code IN %s", (tuple(codes),))
                    rows = cur.fetchall() or []
                    id_by_code = {str(r[1]): int(r[0]) for r in rows}
                    for code in codes:
                        mid = id_by_code.get(code)
                        if mid:
                            cur.execute(
                                "INSERT IGNORE INTO role_menus(role_id, menu_id) VALUES(%s,%s)",
                                (rid, mid),
                            )
            conn.commit()
        return True
    except Exception:
        return False


def get_role_menus(role_code: str) -> list[str]:
    rc = (role_code or "").strip()
    if not rc or not _ensure_tables():
        return []
    ensure_seed_admin()
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM roles WHERE code=%s LIMIT 1", (rc,))
                rr = cur.fetchone()
                if not rr:
                    return []
                rid = int(rr[0])
                cur.execute(
                    """
                    SELECT m.code
                    FROM role_menus rm
                    JOIN menus m ON m.id = rm.menu_id
                    WHERE rm.role_id=%s
                    ORDER BY m.sort_order ASC, m.id ASC
                    """,
                    (rid,),
                )
                rows = cur.fetchall() or []
        return [str(r[0]) for r in rows if r and r[0]]
    except Exception:
        return []


def list_user_menus(user_id: str) -> list[dict[str, Any]]:
    uid = (user_id or "").strip()
    if not uid or not _ensure_tables():
        return []
    ensure_seed_admin()
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT m.code, m.name, m.path, m.icon, m.parent_id, m.sort_order
                    FROM user_roles ur
                    JOIN role_menus rm ON rm.role_id = ur.role_id
                    JOIN menus m ON m.id = rm.menu_id
                    WHERE ur.user_id=%s AND m.enabled=1
                    ORDER BY m.sort_order ASC, m.id ASC
                    """,
                    (uid,),
                )
                rows = cur.fetchall() or []
        return [
            {
                "code": r[0] or "",
                "name": r[1] or "",
                "path": r[2] or "",
                "icon": r[3] or "",
                "parent_id": int(r[4]) if r[4] is not None else None,
                "sort_order": int(r[5] or 0),
            }
            for r in rows
        ]
    except Exception:
        return []

