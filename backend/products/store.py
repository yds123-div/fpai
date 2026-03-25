# -*- coding: utf-8 -*-
"""
基金产品本地存储：
- 同步 AkShare 基金基础列表到本地 MySQL
- 提供分页与模糊查询（按代码/名称/类型）
"""

from __future__ import annotations

from typing import Any

from pkg.logger import get_logger
from pkg.mysql_client import get_connection, is_configured as mysql_configured

logger = get_logger(__name__)


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fund_products (
  product_code VARCHAR(32) NOT NULL,
  product_name VARCHAR(255) NOT NULL DEFAULT '',
  product_type VARCHAR(64) NOT NULL DEFAULT '',
  risk_level VARCHAR(32) NOT NULL DEFAULT '-',
  term VARCHAR(64) NOT NULL DEFAULT '-',
  source VARCHAR(32) NOT NULL DEFAULT 'akshare',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (product_code),
  KEY idx_fund_products_name (product_name),
  KEY idx_fund_products_type (product_type),
  KEY idx_fund_products_updated_at (updated_at)
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
        logger.warning("ensure fund_products table failed: %s", e)
        return False


def upsert_products(items: list[dict[str, Any]]) -> int:
    if not items or not _ensure_table():
        return 0
    normalized: list[tuple[str, str, str, str, str, str]] = []
    for it in items:
        code = str(it.get("code") or it.get("id") or "").strip()
        name = str(it.get("name") or "").strip()
        if not code or not name:
            continue
        normalized.append(
            (
                code,
                name,
                str(it.get("productType") or it.get("type") or "").strip(),
                str(it.get("riskLevel") or "-").strip() or "-",
                str(it.get("term") or "-").strip() or "-",
                str(it.get("source") or "akshare").strip() or "akshare",
            )
        )
    if not normalized:
        return 0
    try:
        with get_connection() as conn:
            if not conn:
                return 0
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO fund_products (product_code, product_name, product_type, risk_level, term, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      product_name=VALUES(product_name),
                      product_type=VALUES(product_type),
                      risk_level=VALUES(risk_level),
                      term=VALUES(term),
                      source=VALUES(source)
                    """,
                    normalized,
                )
            conn.commit()
            return int(cur.rowcount or 0)
    except Exception as e:
        logger.warning("upsert fund products failed: %s", e)
        return 0


def search_products(
    *,
    product_code: str | None,
    product_type: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    if not _ensure_table():
        return [], 0
    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 20), 100))
    offset = (p - 1) * ps

    where_parts: list[str] = []
    params: list[Any] = []
    pc = (product_code or "").strip()
    pt = (product_type or "").strip()
    kw = (keyword or "").strip()
    if pc:
        where_parts.append("product_code LIKE %s")
        params.append(f"%{pc}%")
    if pt:
        where_parts.append("product_type LIKE %s")
        params.append(f"%{pt}%")
    if kw:
        where_parts.append("(product_code LIKE %s OR product_name LIKE %s OR product_type LIKE %s)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    try:
        with get_connection() as conn:
            if not conn:
                return [], 0
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(1) FROM fund_products {where_sql}", tuple(params))
                row = cur.fetchone()
                total = int((row[0] if row else 0) or 0)

                cur.execute(
                    f"""
                    SELECT product_code, product_name, product_type, risk_level, term
                    FROM fund_products
                    {where_sql}
                    ORDER BY updated_at DESC, product_code ASC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params + [ps, offset]),
                )
                rows = cur.fetchall() or []
        out = [
            {
                "id": r[0] or "",
                "name": r[1] or "",
                "productType": r[2] or "",
                "riskLevel": r[3] or "-",
                "term": r[4] or "-",
            }
            for r in rows
        ]
        return out, total
    except Exception as e:
        logger.warning("search fund products failed: %s", e)
        return [], 0
