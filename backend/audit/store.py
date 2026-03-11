"""
审计存储：热数据 MySQL（audit_index + audit_events），冷数据 MinIO；保留 6 个月、按条件导出。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from pkg.logger import get_logger
from pkg.minio_client import (
    get_bucket_audit,
    get_client as get_minio_client,
    put_object,
    get_object,
    ensure_bucket,
    build_object_name,
)
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)

# 保留周期 6 个月（architecture S3）
RETENTION_MONTHS = 6
AUDIT_COLD_TENANT = "default"
AUDIT_COLD_TYPE = "audit"


def _ensure_audit_bucket() -> bool:
    return ensure_bucket(get_bucket_audit())


def append_event(
    answer_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    intent: str | None = None,
    model_version: str | None = None,
    policy_version: str | None = None,
) -> bool:
    """
    追加审计事件；若该 answer_id 在 audit_index 尚无记录则插入索引行（用传入的 session_id/user_id 等）。
    """
    if not mysql_configured():
        logger.warning("MySQL 未配置，审计事件未落库")
        return False
    payload_json = json.dumps(payload, ensure_ascii=False)
    try:
        with get_connection() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                # 若 audit_index 无该 answer_id，先插入索引行
                cur.execute(
                    """SELECT 1 FROM audit_index WHERE answer_id = %s LIMIT 1""",
                    (answer_id,),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        """INSERT INTO audit_index (answer_id, session_id, user_id, intent, model_version, policy_version)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE
                             session_id = IF(VALUES(session_id) != '', VALUES(session_id), session_id),
                             user_id = IF(VALUES(user_id) != '', VALUES(user_id), user_id),
                             intent = IF(VALUES(intent) IS NOT NULL AND VALUES(intent) != '', VALUES(intent), intent),
                             model_version = IF(VALUES(model_version) IS NOT NULL AND VALUES(model_version) != '', VALUES(model_version), model_version),
                             policy_version = IF(VALUES(policy_version) IS NOT NULL AND VALUES(policy_version) != '', VALUES(policy_version), policy_version)""",
                        (
                            answer_id,
                            session_id or "",
                            user_id or "",
                            intent or "",
                            model_version or "",
                            policy_version or "",
                        ),
                    )
                cur.execute(
                    """INSERT INTO audit_events (answer_id, event_type, payload) VALUES (%s, %s, %s)""",
                    (answer_id, event_type, payload_json),
                )
            return True
    except Exception as e:
        logger.exception("append_event 失败: %s", e)
        return False


def get_evidence(answer_id: str) -> dict[str, Any] | None:
    """
    按 answerId 查询证据：热数据从 MySQL 读索引 + 事件；若存在 cold_ref 则从 MinIO 拉取冷数据合并。
    """
    if not mysql_configured():
        return None
    try:
        with get_connection() as conn:
            if conn is None:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT answer_id, session_id, user_id, intent, model_version, policy_version, created_at, cold_ref
                       FROM audit_index WHERE answer_id = %s LIMIT 1""",
                    (answer_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                (
                    aid,
                    session_id,
                    user_id,
                    intent,
                    model_version,
                    policy_version,
                    created_at,
                    cold_ref,
                ) = row
                events: list[dict[str, Any]] = []
                if cold_ref:
                    # 冷数据：从 MinIO 读取事件列表
                    bucket = get_bucket_audit()
                    raw = get_object(bucket, cold_ref)
                    if raw:
                        try:
                            cold_data = json.loads(raw.decode("utf-8"))
                            events = cold_data.get("events") or []
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                else:
                    cur.execute(
                        """SELECT event_type, payload, created_at FROM audit_events WHERE answer_id = %s ORDER BY created_at ASC""",
                        (answer_id,),
                    )
                    for event_type, payload_str, evt_at in cur.fetchall():
                        try:
                            pl = json.loads(payload_str) if isinstance(payload_str, str) else (payload_str or {})
                        except (TypeError, json.JSONDecodeError):
                            pl = {}
                        events.append({
                            "event_type": event_type,
                            "payload": pl,
                            "created_at": evt_at.isoformat() + "Z" if evt_at and getattr(evt_at, "isoformat", None) else None,
                        })
                return {
                    "answer_id": aid,
                    "session_id": session_id or "",
                    "user_id": user_id or "",
                    "intent": intent,
                    "model_version": model_version,
                    "policy_version": policy_version,
                    "created_at": created_at.isoformat() + "Z" if created_at and getattr(created_at, "isoformat", None) else None,
                    "cold_ref": cold_ref,
                    "events": events,
                }
    except Exception as e:
        logger.exception("get_evidence 失败: %s", e)
        return None


def archive_to_cold(answer_id: str) -> bool:
    """
    将某 answer_id 的热事件归档到 MinIO，更新 audit_index.cold_ref，并删除 audit_events 对应行。
    """
    if not mysql_configured():
        return False
    try:
        with get_connection() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT event_type, payload, created_at FROM audit_events WHERE answer_id = %s ORDER BY created_at ASC""",
                    (answer_id,),
                )
                rows = cur.fetchall()
                if not rows:
                    return True
                events = []
                for event_type, payload_str, evt_at in rows:
                    try:
                        pl = json.loads(payload_str) if isinstance(payload_str, str) else (payload_str or {})
                    except (TypeError, json.JSONDecodeError):
                        pl = {}
                    events.append({
                        "event_type": event_type,
                        "payload": pl,
                        "created_at": evt_at.isoformat() if evt_at and getattr(evt_at, "isoformat", None) else None,
                    })
                # 生成冷存储路径：default/audit/YYYY-MM/answer_id
                now = datetime.utcnow()
                year_month = now.strftime("%Y-%m")
                object_name = build_object_name(AUDIT_COLD_TENANT, AUDIT_COLD_TYPE, year_month, answer_id)
                bucket = get_bucket_audit()
                if get_minio_client() and _ensure_audit_bucket():
                    body = json.dumps({"answer_id": answer_id, "events": events}, ensure_ascii=False).encode("utf-8")
                    if not put_object(bucket, object_name, body, content_type="application/json"):
                        return False
                else:
                    object_name = ""  # MinIO 不可用时仅删热数据，不设 cold_ref
                cur.execute("""UPDATE audit_index SET cold_ref = %s WHERE answer_id = %s""", (object_name or None, answer_id))
                cur.execute("""DELETE FROM audit_events WHERE answer_id = %s""", (answer_id,))
            return True
    except Exception as e:
        logger.exception("archive_to_cold 失败: %s", e)
        return False


def list_answer_ids_for_retention(older_than_days: int = RETENTION_MONTHS * 30) -> list[str]:
    """返回 created_at 早于 older_than_days 天的 answer_id 列表，供归档或清理。"""
    if not mysql_configured():
        return []
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.answer_id FROM audit_index a
                       INNER JOIN audit_events e ON e.answer_id = a.answer_id
                       WHERE a.created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                       AND (a.cold_ref IS NULL OR a.cold_ref = '')
                       GROUP BY a.answer_id
                       ORDER BY MIN(a.created_at) ASC""",
                    (older_than_days,),
                )
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.exception("list_answer_ids_for_retention 失败: %s", e)
        return []


def export_report(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    answer_ids: list[str] | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """
    按条件导出审计报告：时间范围、用户、会话、answer_id；返回证据列表（含 events）。
    """
    if not mysql_configured():
        return []
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                sql = """SELECT answer_id, session_id, user_id, intent, model_version, policy_version, created_at, cold_ref
                         FROM audit_index WHERE 1=1"""
                params: list[Any] = []
                if since:
                    sql += " AND created_at >= %s"
                    params.append(since)
                if until:
                    sql += " AND created_at <= %s"
                    params.append(until)
                if user_id:
                    sql += " AND user_id = %s"
                    params.append(user_id)
                if session_id:
                    sql += " AND session_id = %s"
                    params.append(session_id)
                if answer_ids:
                    placeholders = ",".join(["%s"] * len(answer_ids))
                    sql += f" AND answer_id IN ({placeholders})"
                    params.extend(answer_ids)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, params)
                rows = cur.fetchall()
            result = []
            for row in rows:
                (aid, sid, uid, intent, mv, pv, created_at, cold_ref) = row
                ev = get_evidence(aid)
                if ev:
                    result.append(ev)
            return result
    except Exception as e:
        logger.exception("export_report 失败: %s", e)
        return []
