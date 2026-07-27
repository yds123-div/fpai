# -*- coding: utf-8 -*-
"""
用户与认证服务：账号密码校验、Token 签发与校验；供鉴权中间件校验 Token 并注入 userId（users.id）。

T027a：见 technical_design §2.1、§2.3 登录契约与 §4.1 users 表。
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# 与前端 crypto 约定：前端发送 SHA256(明文密码) 的 hex 字符串，后端存储 bcrypt(SHA256(明文))
def _sha256_hex(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)

# 密码哈希：使用标准库 bcrypt，避免 passlib 与 bcrypt 版本不兼容
try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None  # type: ignore[assignment]
    _BCRYPT_AVAILABLE = False

BCRYPT_ROUNDS = 12

# JWT
try:
    import jwt
    _JWT_AVAILABLE = True
except ImportError:
    jwt = None  # type: ignore[assignment]
    _JWT_AVAILABLE = False

# 环境变量
JWT_SECRET_ENV = "JWT_SECRET"
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_SECONDS = int(os.getenv("JWT_EXPIRES_SECONDS", "86400"))  # 24h


def hash_password(plain: str) -> str:
    """
    将明文密码哈希为存储格式；用于注册或种子数据。
    与前端约定：前端登录时发送 SHA256(明文).hex，此处存储 bcrypt(SHA256(明文).hex)，以便登录时直接比对。
    未安装 bcrypt 时返回空字符串。
    """
    if not _BCRYPT_AVAILABLE or not plain:
        return ""
    digest = _sha256_hex(plain)
    salt = _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return _bcrypt.hashpw(digest.encode("utf-8"), salt).decode("ascii")


def hash_password_from_digest(digest_hex: str) -> str:
    """
    将已是 SHA256(明文).hex 的字符串用 bcrypt 哈希后存储。
    用于当前用户修改密码时，前端传入 new_password 为 SHA256(新密码).hex，与登录约定一致。
    """
    if not _BCRYPT_AVAILABLE or not (digest_hex or "").strip():
        return ""
    digest_hex = digest_hex.strip()
    salt = _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return _bcrypt.hashpw(digest_hex.encode("utf-8"), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """
    校验「待校验值」与存储哈希是否匹配。
    plain: 前端登录时发送的 SHA256(明文).hex；
    hashed: 经 hash_password 得到的 bcrypt(SHA256(明文).hex)。
    使用 bcrypt.checkpw 进行安全比对。
    """
    if not _BCRYPT_AVAILABLE:
        return False
    if not hashed or not hashed.strip() or not plain:
        return False
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False

def verify_user(account: str, password: str) -> dict[str, Any] | None:
    """按账号与密码校验用户；成功返回用户记录，失败返回 None。"""
    account = (account or "").strip()
    password = password or ""
    if not mysql_configured():
        return None
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, account, password_hash, name, employee_no, email
                       FROM users WHERE account = %s LIMIT 1""",
                    (account,),
                )
                row = cur.fetchone()
        if not row:
            return None
        user_id, acc, password_hash_val, name, employee_no, email = row
        if not verify_password(password, password_hash_val or ""):
            return None
        return {
            "id": user_id,
            "account": acc or "",
            "name": name or "",
            "employee_no": employee_no or "",
            "email": email or "",
        }
    except Exception as e:
        logger.warning("verify_user 失败: %s", e)
        return None


def issue_token(user_id: str) -> str:
    """
    签发 JWT；payload 含 sub=user_id、exp、iat。
    未配置 JWT_SECRET 或未安装 pyjwt 时返回空字符串。
    """
    if not _JWT_AVAILABLE:
        return ""
    secret = (os.getenv(JWT_SECRET_ENV) or "").strip()
    if not secret:
        logger.warning("JWT_SECRET 未配置，无法签发 Token")
        return ""
    now = datetime.now(timezone.utc)
    payload = {
        # PyJWT 会校验 sub 必须为字符串；这里统一转为 str，避免 users.id 为数值时导致 token 无效
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=JWT_EXPIRES_SECONDS),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    """
    校验并解析 JWT；成功返回 payload（含 sub 即 userId），失败返回 None。
    供鉴权中间件解析 Token 并注入 userId。
    """
    token = (token or "").strip()
    if not token or not _JWT_AVAILABLE:
        return None
    secret = (os.getenv(JWT_SECRET_ENV) or "").strip()
    if not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        if isinstance(payload, dict) and payload.get("sub"):
            return payload
    except jwt.ExpiredSignatureError:
        pass
    except Exception:
        pass
    return None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """按 users.id 查询用户信息（不含密码）；不存在返回 None。"""
    user_id = (user_id or "").strip()
    if not user_id or not mysql_configured():
        return None
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, account, name, employee_no, email FROM users WHERE id = %s LIMIT 1""",
                    (user_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "account": row[1] or "",
            "name": row[2] or "",
            "employee_no": row[3] or "",
            "email": row[4] or "",
        }
    except Exception as e:
        logger.warning("get_user_by_id 失败: %s", e)
        return None


def get_password_hash_by_user_id(user_id: str) -> str | None:
    """按 users.id 查询 password_hash；不存在或未配置返回 None。用于修改密码时校验旧密码。"""
    user_id = (user_id or "").strip()
    if not user_id or not mysql_configured():
        return None
    try:
        with get_connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT password_hash FROM users WHERE id = %s LIMIT 1""",
                    (user_id,),
                )
                row = cur.fetchone()
        return (row[0] or "").strip() if row and row[0] else None
    except Exception as e:
        logger.warning("get_password_hash_by_user_id 失败: %s", e)
        return None


def update_user_password_hash(user_id: str, new_password_hash: str) -> bool:
    """更新指定用户的 password_hash。成功返回 True。"""
    user_id = (user_id or "").strip()
    if not user_id or not (new_password_hash or "").strip() or not mysql_configured():
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE users SET password_hash = %s WHERE id = %s""",
                    (new_password_hash.strip(), user_id),
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.warning("update_user_password_hash 失败: %s", e)
        return False


# ---------- 用户管理：分页查询、新增、修改、删除、重置密码 ----------


def _row_to_user(row: tuple) -> dict[str, Any]:
    """将 users 表一行转为不含 password_hash 的 user 字典。"""
    return {
        "id": str(row[0]) if row[0] is not None else "",
        "account": row[1] or "",
        "name": row[2] or "",
        "employee_no": row[3] or "",
        "email": row[4] or "",
    }


def list_users_paginated(
    page: int = 1,
    page_size: int = 10,
    account_like: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    分页查询用户列表（不含 password_hash）。
    返回 (items, total)。
    """
    if not mysql_configured():
        return [], 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size
    try:
        with get_connection() as conn:
            if not conn:
                return [], 0
            with conn.cursor() as cur:
                if account_like and account_like.strip():
                    like = f"%{account_like.strip()}%"
                    cur.execute(
                        """SELECT COUNT(*) FROM users WHERE account LIKE %s""",
                        (like,),
                    )
                    total = cur.fetchone()[0] or 0
                    cur.execute(
                        """SELECT id, account, name, employee_no, email
                           FROM users WHERE account LIKE %s ORDER BY id LIMIT %s OFFSET %s""",
                        (like, page_size, offset),
                    )
                else:
                    cur.execute("""SELECT COUNT(*) FROM users""")
                    total = cur.fetchone()[0] or 0
                    cur.execute(
                        """SELECT id, account, name, employee_no, email
                           FROM users ORDER BY id LIMIT %s OFFSET %s""",
                        (page_size, offset),
                    )
                rows = cur.fetchall()
        return [_row_to_user(r) for r in rows], total
    except Exception as e:
        logger.warning("list_users_paginated 失败: %s", e)
        return [], 0


# 唯一性校验：返回冲突的字段名（account/name/email/employee_no），仅对非空值校验；无冲突返回 None
_FIELD_INDEX = {"account": 1, "name": 2, "employee_no": 3, "email": 4}


def _find_unique_conflict(
    cur: Any,
    account: str | None = None,
    name: str | None = None,
    employee_no: str | None = None,
    email: str | None = None,
    exclude_user_id: str | None = None,
) -> str | None:
    """检查 account/name/email/employee_no 是否与已有用户冲突（非空才校验）。返回冲突字段名或 None。"""
    checks: list[tuple[str, str]] = []
    if account is not None and (account or "").strip():
        checks.append(("account", (account or "").strip()))
    if name is not None and (name or "").strip():
        checks.append(("name", (name or "").strip()))
    if employee_no is not None and (employee_no or "").strip():
        checks.append(("employee_no", (employee_no or "").strip()))
    if email is not None and (email or "").strip():
        checks.append(("email", (email or "").strip()))
    if not checks:
        return None
    conditions = " OR ".join([f"{f} = %s" for f, _ in checks])
    params: list[Any] = [v for _, v in checks]
    if exclude_user_id:
        conditions = "id != %s AND (" + conditions + ")"
        params = [exclude_user_id] + params
    cur.execute(
        f"""SELECT id, account, name, employee_no, email FROM users WHERE {conditions} LIMIT 1""",
        params,
    )
    row = cur.fetchone()
    if not row:
        return None
    for field_name, value in checks:
        if row[_FIELD_INDEX[field_name]] == value:
            return field_name
    return checks[0][0]


def create_user(
    account: str,
    password: str,
    name: str = "",
    employee_no: str = "",
    email: str = "",
) -> tuple[dict[str, Any] | None, str | None]:
    """
    新增用户；account、name、email、employee_no 均须唯一（非空时校验）。密码经 hash_password 后入库。
    成功返回 (用户信息, None)；唯一性冲突返回 (None, 冲突字段名)；其他失败返回 (None, None)。
    """
    account = (account or "").strip()
    password = (password or "").strip()
    name_s = (name or "").strip()
    employee_no_s = (employee_no or "").strip()
    email_s = (email or "").strip()
    if not account:
        return None, None
    if not mysql_configured():
        return None, None
    pwd_hash = hash_password(password) if password else ""
    if not pwd_hash and _BCRYPT_AVAILABLE:
        return None, None
    try:
        with get_connection() as conn:
            if not conn:
                return None, None
            with conn.cursor() as cur:
                conflict = _find_unique_conflict(cur, account=account, name=name_s or None, employee_no=employee_no_s or None, email=email_s or None)
                if conflict:
                    return None, conflict

                # 优先：让数据库自增/生成主键（不显式插入 id）
                # 回退：若你的库里 users.id 不是自增（例如 VARCHAR 主键无默认值），再显式插入 u_{uuid}。
                try:
                    cur.execute(
                        """INSERT INTO users (account, password_hash, name, employee_no, email)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (account, pwd_hash, name_s, employee_no_s, email_s),
                    )
                except Exception as e:
                    # 仅在 "id 没有默认值"（例如 VARCHAR 主键无默认值）时才回退写入 id。
                    # 这样在 users.id 为 INT AUTO_INCREMENT 时不会误触发 u_{uuid} 回退。
                    msg = str(e)
                    if ("doesn't have a default value" in msg) or ("Field 'id'" in msg):
                        user_id = "u_" + uuid.uuid4().hex
                        cur.execute(
                            """INSERT INTO users (id, account, password_hash, name, employee_no, email)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (user_id, account, pwd_hash, name_s, employee_no_s, email_s),
                        )
                    else:
                        raise
                conn.commit()
        with get_connection() as conn2:
            if not conn2:
                return None, None
            with conn2.cursor() as cur2:
                cur2.execute(
                    """SELECT id, account, name, employee_no, email FROM users WHERE account = %s LIMIT 1""",
                    (account,),
                )
                row = cur2.fetchone()
        if not row:
            return None, None
        return _row_to_user(row), None
    except Exception as e:
        logger.warning("create_user 失败: %s", e)
        return None, None


def update_user(
    user_id: str,
    account: str | None = None,
    name: str | None = None,
    employee_no: str | None = None,
    email: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    更新用户信息（account、name、employee_no、email）；不修改密码。
    成功返回 (更新后用户信息, None)；唯一性冲突返回 (None, 冲突字段名)；其他失败返回 (None, None)。
    """
    user_id = (user_id or "").strip()
    if not user_id or not mysql_configured():
        return None, None
    try:
        with get_connection() as conn:
            if not conn:
                return None, None
            with conn.cursor() as cur:
                updates = []
                params: list[Any] = []
                if account is not None:
                    updates.append("account = %s")
                    params.append((account or "").strip())
                if name is not None:
                    updates.append("name = %s")
                    params.append((name or "").strip())
                if employee_no is not None:
                    updates.append("employee_no = %s")
                    params.append((employee_no or "").strip())
                if email is not None:
                    updates.append("email = %s")
                    params.append((email or "").strip())
                if not updates:
                    return get_user_by_id(user_id), None
                acc_val = (account or "").strip() if account is not None else None
                name_val = (name or "").strip() if name is not None else None
                emp_val = (employee_no or "").strip() if employee_no is not None else None
                email_val = (email or "").strip() if email is not None else None
                conflict = _find_unique_conflict(cur, account=acc_val, name=name_val, employee_no=emp_val, email=email_val, exclude_user_id=user_id)
                if conflict:
                    return None, conflict
                params = []
                if account is not None:
                    params.append((account or "").strip())
                if name is not None:
                    params.append((name or "").strip())
                if employee_no is not None:
                    params.append((employee_no or "").strip())
                if email is not None:
                    params.append((email or "").strip())
                params.append(user_id)
                cur.execute(
                    f"""UPDATE users SET {", ".join(updates)} WHERE id = %s""",
                    params,
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None, None
        return get_user_by_id(user_id), None
    except Exception as e:
        logger.warning("update_user 失败: %s", e)
        return None, None


def delete_user(user_id: str) -> bool:
    """删除用户；成功返回 True。"""
    user_id = (user_id or "").strip()
    if not user_id or not mysql_configured():
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute("""DELETE FROM users WHERE id = %s""", (user_id,))
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.warning("delete_user 失败: %s", e)
        return False


def reset_user_password(user_id: str, new_password_plain: str) -> bool:
    """重置用户密码（明文）；经 hash_password 后更新。成功返回 True。"""
    user_id = (user_id or "").strip()
    new_password_plain = (new_password_plain or "").strip()
    if not user_id or not new_password_plain:
        return False
    pwd_hash = hash_password(new_password_plain)
    if not pwd_hash:
        return False
    if not mysql_configured():
        return False
    try:
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE users SET password_hash = %s WHERE id = %s""",
                    (pwd_hash, user_id),
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.warning("reset_user_password 失败: %s", e)
        return False
