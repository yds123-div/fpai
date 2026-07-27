# -*- coding: utf-8 -*-
"""
会话服务：会话创建、消息持久化、会话上下文（Redis session:{id}）；会话内 productIds、customerProfile 参与编排。

T027：见 architecture Conversation Service、technical_design §4.1/§4.2。
"""
from __future__ import annotations

import uuid
import re
from datetime import datetime, timezone
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured
from pkg.redis_keys import (
    session_context_get,
    session_context_set,
    session_context_refresh,
    DEFAULT_SESSION_TTL,
)

logger = get_logger(__name__)

# Redis 会话上下文字段（与编排/chat 契约一致）
CTX_USER_ID = "user_id"
CTX_PRODUCT_IDS = "product_ids"
CTX_CUSTOMER_PROFILE = "customer_profile"
CTX_UPDATED_AT = "updated_at"

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_context(user_id: str = "") -> dict[str, Any]:
    return {
        CTX_USER_ID: user_id or "",
        CTX_PRODUCT_IDS: [],
        CTX_CUSTOMER_PROFILE: "",
        CTX_UPDATED_AT: _now_iso(),
    }


def create_session(user_id: str) -> str:
    """
    创建会话：写入 MySQL sessions 表，并初始化 Redis session:{id} 上下文（user_id、product_ids、customer_profile）。

    Returns:
        session_id: 新会话 ID；MySQL 未配置时仍返回 id 并仅写 Redis。
    """
    session_id = uuid.uuid4().hex
    if mysql_configured():
        try:
            with get_connection() as conn:
                if conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO sessions (id, user_id) VALUES (%s, %s)""",
                            (session_id, user_id or ""),
                        )
        except Exception as e:
            logger.warning("会话写入 MySQL 失败: %s", e)
    ctx = _default_context(user_id)
    session_context_set(session_id, ctx, ttl_seconds=DEFAULT_SESSION_TTL)
    return session_id


def _ensure_session_in_mysql(session_id: str) -> None:
    """
    若 MySQL 中不存在该 session_id，则插入一行，避免 messages 外键失败。
    用于会话仅存在于 Redis（如创建时 MySQL 不可用或客户端传入旧 session_id）时补写 sessions 表。
    """
    if not session_id or not mysql_configured():
        return
    try:
        ctx = session_context_get(session_id)
        user_id = (ctx.get(CTX_USER_ID) or "") if isinstance(ctx, dict) else ""
        with get_connection() as conn:
            if not conn:
                return
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT IGNORE INTO sessions (id, user_id) VALUES (%s, %s)""",
                    (session_id, user_id or ""),
                )
    except Exception:
        pass


def get_session(session_id: str) -> dict[str, Any] | None:
    """
    获取会话：先读 Redis 上下文；若 MySQL 可用则补充 sessions 表字段（created_at、updated_at）。

    Returns:
        含 id、user_id、product_ids、customer_profile、created_at、updated_at 的 dict；不存在或无效时返回 None。
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return None
    ctx = session_context_get(session_id)
    if ctx is None:
        if mysql_configured():
            try:
                with get_connection() as conn:
                    if conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """SELECT id, user_id, created_at, updated_at FROM sessions WHERE id = %s LIMIT 1""",
                                (session_id,),
                            )
                            row = cur.fetchone()
                            if row:
                                ctx = _default_context(row[1])
                                session_context_set(session_id, ctx, ttl_seconds=DEFAULT_SESSION_TTL)
                            else:
                                return None
            except Exception as e:
                logger.warning("会话查询 MySQL 失败: %s", e)
                return None
        else:
            return None
    if not isinstance(ctx, dict):
        return None
    out = {
        "id": session_id,
        "user_id": ctx.get(CTX_USER_ID) or "",
        "product_ids": ctx.get(CTX_PRODUCT_IDS) if isinstance(ctx.get(CTX_PRODUCT_IDS), list) else [],
        "customer_profile": ctx.get(CTX_CUSTOMER_PROFILE) or "",
        "created_at": None,
        "updated_at": ctx.get(CTX_UPDATED_AT),
    }
    if mysql_configured():
        try:
            with get_connection() as conn:
                if conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT created_at, updated_at FROM sessions WHERE id = %s LIMIT 1""",
                            (session_id,),
                        )
                        row = cur.fetchone()
                        if row:
                            out["created_at"] = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
                            out["updated_at"] = row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
        except Exception as e:
            pass
    return out


def get_session_context_for_orchestration(session_id: str) -> dict[str, Any]:
    """
    获取供编排使用的会话上下文：product_ids、customer_profile，用于 T026 run_chat_turn 的 product_ids/customer_profile 参数。

    若 session_id 为空或会话不存在，返回空 dict。
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return {}
    ctx = session_context_get(session_id)
    if not isinstance(ctx, dict):
        return {}
    product_ids = ctx.get(CTX_PRODUCT_IDS)
    if not isinstance(product_ids, list):
        product_ids = []
    customer_profile = ctx.get(CTX_CUSTOMER_PROFILE) or ""
    return {
        "product_ids": product_ids,
        "customer_profile": customer_profile,
    }


def update_session_context(
    session_id: str,
    *,
    product_ids: list[str] | None = None,
    customer_profile: str | None = None,
) -> bool:
    """
    更新会话上下文（Redis）：合并 product_ids、customer_profile，并续期 TTL。
    用于 chat 请求体中的 productIds、customerProfile 写回会话。
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return False
    ctx = session_context_get(session_id)
    if not isinstance(ctx, dict):
        ctx = _default_context("")
    if product_ids is not None:
        ctx[CTX_PRODUCT_IDS] = [str(x) for x in product_ids]
    if customer_profile is not None:
        ctx[CTX_CUSTOMER_PROFILE] = str(customer_profile).strip()
    ctx[CTX_UPDATED_AT] = _now_iso()
    ok = session_context_set(session_id, ctx, ttl_seconds=DEFAULT_SESSION_TTL)
    if ok:
        session_context_refresh(session_id, ttl_seconds=DEFAULT_SESSION_TTL)
    return ok


def append_message(
    session_id: str,
    role: str,
    content_summary: str,
    *,
    answer_id: str | None = None,
    citation_count: int = 0,
    full_content: str | None = None,
    structured_outputs: list[dict[str, Any]] | None = None,
) -> bool:
    """持久化一条消息到 MySQL messages 表；并续期 Redis 会话 TTL。"""
    session_id = (session_id or "").strip()
    if not session_id:
        return False
    role = (role or "user").lower()
    if role not in ("user", "assistant"):
        role = "user"
    content_summary = (content_summary or "")[:2000]
    if not mysql_configured():
        logger.warning(
            "[RCA][session] append_message skipped mysql persistence: mysql not configured, session_id=%s, role=%s, answer_id=%s",
            session_id[:8],
            role,
            (answer_id or "")[:8],
        )
        session_context_refresh(session_id, ttl_seconds=DEFAULT_SESSION_TTL)
        return True
    try:
        _ensure_session_in_mysql(session_id)
        with get_connection() as conn:
            if not conn:
                return False
            with conn.cursor() as cur:
                import json as _json
                so_json = _json.dumps(structured_outputs) if structured_outputs else None
                cur.execute(
                    """INSERT INTO messages (session_id, role, content_summary, full_content, structured_outputs, answer_id, citation_count)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (session_id, role, content_summary, full_content or None, so_json, answer_id or None, max(0, citation_count)),
                )
        session_context_refresh(session_id, ttl_seconds=DEFAULT_SESSION_TTL)
        return True
    except Exception as e:
        logger.warning("消息持久化失败: %s", e)
        return False


def get_recent_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    获取会话最近若干条消息，用于上下文或洞察；按 created_at 倒序。

    Returns:
        list of {role, content_summary, answer_id, citation_count, created_at}
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return []
    if not mysql_configured():
        logger.warning(
            "[RCA][session] get_recent_messages returns empty: mysql not configured, session_id=%s, limit=%s",
            session_id[:8],
            limit,
        )
        return []
    limit = max(1, min(limit, 100))
    try:
        with get_connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT role, content_summary, full_content, structured_outputs, answer_id, citation_count, created_at
                       FROM messages WHERE session_id = %s ORDER BY created_at DESC LIMIT %s""",
                    (session_id, limit),
                )
                rows = cur.fetchall()
        out = []
        for row in rows:
            created = row[6]
            so_raw = row[3]
            so_parsed = None
            if so_raw:
                try:
                    import json as _json
                    so_parsed = _json.loads(so_raw) if isinstance(so_raw, str) else so_raw
                except Exception:
                    so_parsed = None
            out.append({
                "role": row[0] or "user",
                "content_summary": row[1] or "",
                "full_content": row[2],
                "structured_outputs": so_parsed,
                "answer_id": row[4],
                "citation_count": row[5] or 0,
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
            })
        return out
    except Exception as e:
        logger.warning("会话消息查询失败: %s", e)
        return []


def list_user_sessions(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    mysql_connect_timeout: int = 3,
    mysql_read_timeout: int = 5,
    mysql_write_timeout: int = 5,
    query_timeout_ms: int = 3000,
) -> tuple[list[dict[str, Any]], int]:
    """
    按用户分页查询会话列表（包含无消息会话）。

    返回:
      items: [{session_id, created_at, last_message_at, last_message_preview}, ...]
      total: 该用户会话总数
    """
    uid = (user_id or "").strip()
    if not uid:
        return [], 0

    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 20), 100))
    offset = (p - 1) * ps

    if not mysql_configured():
        logger.warning("[sessions/list] mysql not configured, user_id=%s", uid[:8])
        return [], 0

    try:
        with get_connection(
            connect_timeout=max(1, int(mysql_connect_timeout or 3)),
            read_timeout=max(1, int(mysql_read_timeout or 5)),
            write_timeout=max(1, int(mysql_write_timeout or 5)),
        ) as conn:
            if not conn:
                logger.warning("[sessions/list] mysql connection unavailable, user_id=%s", uid[:8])
                return [], 0
            with conn.cursor() as cur:
                # 查询级超时：避免单次 SQL 长时间占用线程
                try:
                    cur.execute("SET SESSION MAX_EXECUTION_TIME = %s", (max(100, int(query_timeout_ms or 3000)),))
                except Exception:
                    pass
                cur.execute(
                    """SELECT COUNT(1)
                       FROM sessions
                       WHERE user_id = %s""",
                    (uid,),
                )
                total_row = cur.fetchone()
                total = int((total_row[0] if total_row else 0) or 0)

                cur.execute(
                    """SELECT
                           s.id AS session_id,
                           s.created_at AS created_at,
                           COALESCE(
                             (
                               SELECT MAX(m.created_at)
                               FROM messages m
                               WHERE m.session_id = s.id
                             ),
                             s.created_at
                           ) AS last_message_at,
                           (
                             SELECT COALESCE(NULLIF(m2.full_content, ''), m2.content_summary)
                             FROM messages m2
                             WHERE m2.session_id = s.id
                             ORDER BY m2.created_at DESC, m2.id DESC
                             LIMIT 1
                           ) AS last_message_preview
                       FROM sessions s
                       WHERE s.user_id = %s
                       ORDER BY last_message_at DESC
                       LIMIT %s OFFSET %s""",
                    (uid, ps, offset),
                )
                rows = cur.fetchall() or []

        items: list[dict[str, Any]] = []
        for row in rows:
            created = row[1]
            last_at = row[2]
            preview_raw = row[3] if row[3] is not None else ""
            preview_cleaned = _sanitize_preview_text(preview_raw)
            items.append(
                {
                    "session_id": row[0] or "",
                    "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                    "last_message_at": last_at.isoformat() if hasattr(last_at, "isoformat") else str(last_at or ""),
                    "last_message_preview": preview_cleaned,
                }
            )
        return items, total
    except Exception as e:
        logger.warning("[sessions/list] query failed error=%s", e, exc_info=True)
        return [], 0


def _sanitize_preview_text(raw: Any, max_len: int = 96) -> str:
    """
    清洗会话预览文本：
    - 去掉 <think>...</think> 块
    - 去掉未闭合的 <think> 到结尾
    - 折叠空白
    - 截断为侧栏友好长度
    """
    text = str(raw or "")
    if not text:
        return ""
    text = _THINK_BLOCK_RE.sub(" ", text)
    text = _THINK_OPEN_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if len(text) > max_len:
        return text[:max_len].rstrip() + "…"
    return text


def delete_user_session(
    session_id: str,
    user_id: str,
    *,
    mysql_connect_timeout: int = 3,
    mysql_read_timeout: int = 5,
    mysql_write_timeout: int = 5,
) -> str:
    """
    删除当前用户会话（硬删除）：
    - not_found: 会话不存在
    - forbidden: 会话不属于当前用户
    - deleted: 删除成功
    - error: 删除异常
    """
    sid = (session_id or "").strip()
    uid = (user_id or "").strip()
    if not sid:
        return "not_found"
    if not uid:
        return "forbidden"
    if not mysql_configured():
        logger.warning("[sessions/delete] mysql not configured")
        return "error"
    try:
        with get_connection(
            connect_timeout=max(1, int(mysql_connect_timeout or 3)),
            read_timeout=max(1, int(mysql_read_timeout or 5)),
            write_timeout=max(1, int(mysql_write_timeout or 5)),
        ) as conn:
            if not conn:
                logger.warning("[sessions/delete] mysql connection unavailable")
                return "error"
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT user_id FROM sessions WHERE id = %s LIMIT 1 FOR UPDATE""",
                    (sid,),
                )
                row = cur.fetchone()
                if not row:
                    return "not_found"
                owner = str(row[0] or "").strip()
                if owner != uid:
                    return "forbidden"
                cur.execute("""DELETE FROM messages WHERE session_id = %s""", (sid,))
                cur.execute("""DELETE FROM sessions WHERE id = %s""", (sid,))
        # 尽力清理 Redis 上下文；失败不影响删除主结果
        try:
            from pkg.redis_keys import session_context_delete
            session_context_delete(sid)
        except Exception:
            pass
        return "deleted"
    except Exception as e:
        logger.warning("[sessions/delete] failed error=%s", e, exc_info=True)
        return "error"
