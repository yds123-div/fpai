"""
反馈闭环：落库（answerId、userId、rating、comment）、查询与统计。
依据 technical_design §4.1、POST /api/v1/feedback。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

from feedback.types import FeedbackRecord, Rating

logger = get_logger(__name__)

VALID_RATINGS = {r.value for r in Rating}


def _iso_created_at(dt: Any) -> str | None:
    if dt is None or not getattr(dt, "isoformat", None):
        return None
    return dt.isoformat() + "Z" if getattr(dt, "tzinfo", None) is None else dt.isoformat()


def submit_feedback(
    answer_id: str,
    user_id: str,
    rating: str,
    comment: str | None = None,
) -> bool:
    """
    提交反馈并落库；rating 须为 useful / not_useful / inaccurate。
    返回是否落库成功。
    """
    if not answer_id or not user_id or not rating:
        return False
    r = rating.strip().lower()
    if r not in VALID_RATINGS:
        logger.warning("无效 rating: %s", rating)
        return False
    if not mysql_configured():
        logger.warning("MySQL 未配置，反馈未落库")
        return False
    try:
        with get_connection() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO feedback (answer_id, user_id, rating, comment) VALUES (%s, %s, %s, %s)""",
                    (answer_id, user_id, r, (comment or "").strip() or None),
                )
            return True
    except Exception as e:
        logger.exception("submit_feedback 失败: %s", e)
        return False


def list_by_answer_id(answer_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """按 answer_id 查询反馈列表，按创建时间倒序。"""
    if not answer_id or not mysql_configured():
        return []
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, answer_id, user_id, rating, comment, created_at
                       FROM feedback WHERE answer_id = %s ORDER BY created_at DESC LIMIT %s""",
                    (answer_id, max(1, min(limit, 1000))),
                )
                rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "answer_id": row[1],
                    "user_id": row[2],
                    "rating": row[3],
                    "comment": row[4],
                    "created_at": _iso_created_at(row[5]),
                }
                for row in rows
            ]
    except Exception as e:
        logger.exception("list_by_answer_id 失败: %s", e)
        return []


def list_by_user_id(user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """按 user_id 查询反馈列表，按创建时间倒序。"""
    if not user_id or not mysql_configured():
        return []
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, answer_id, user_id, rating, comment, created_at
                       FROM feedback WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
                    (user_id, max(1, min(limit, 1000))),
                )
                rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "answer_id": row[1],
                    "user_id": row[2],
                    "rating": row[3],
                    "comment": row[4],
                    "created_at": _iso_created_at(row[5]),
                }
                for row in rows
            ]
    except Exception as e:
        logger.exception("list_by_user_id 失败: %s", e)
        return []


def get_stats(
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """
    统计反馈：各 rating 数量、总数、有用率（useful / total）。
    可选时间范围 since/until。
    """
    if not mysql_configured():
        return {"useful": 0, "not_useful": 0, "inaccurate": 0, "total": 0, "useful_rate": 0.0}
    try:
        with get_connection() as conn:
            if conn is None:
                return {"useful": 0, "not_useful": 0, "inaccurate": 0, "total": 0, "useful_rate": 0.0}
            with conn.cursor() as cur:
                sql = """SELECT rating, COUNT(*) FROM feedback WHERE 1=1"""
                params: list[Any] = []
                if since:
                    sql += " AND created_at >= %s"
                    params.append(since)
                if until:
                    sql += " AND created_at <= %s"
                    params.append(until)
                sql += " GROUP BY rating"
                cur.execute(sql, params)
                rows = cur.fetchall()
            counts = {"useful": 0, "not_useful": 0, "inaccurate": 0}
            for rating, cnt in rows:
                if rating in counts:
                    counts[rating] = int(cnt)
            total = sum(counts.values())
            useful_rate = (counts["useful"] / total) if total else 0.0
            return {
                **counts,
                "total": total,
                "useful_rate": round(useful_rate, 4),
            }
    except Exception as e:
        logger.exception("get_stats 失败: %s", e)
        return {"useful": 0, "not_useful": 0, "inaccurate": 0, "total": 0, "useful_rate": 0.0}
