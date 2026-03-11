#!/usr/bin/env python3
"""
MySQL 迁移运行器：按顺序执行 scripts/migrations/*.sql，并记录已应用版本。

从项目根目录执行：python scripts/run_migrations.py
依赖 backend 目录下 .env（或项目根 .env），需配置 MYSQL_*。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# 项目根目录（scripts 的上级）
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# 加载 .env：优先 backend/.env，其次项目根 .env
def _load_dotenv():
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

_load_dotenv()

from pkg.mysql_client import get_connection, is_configured


MIGRATIONS_DIR = ROOT / "scripts" / "migrations"
SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `version` VARCHAR(64) NOT NULL PRIMARY KEY,
  `name` VARCHAR(255) NOT NULL,
  `applied_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _version_from_name(name: str) -> str | None:
    m = re.match(r"^(\d+)_", name)
    return m.group(1) if m else None


def _split_sql(content: str) -> list[str]:
    statements = []
    current = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        current.append(line)
        if line.endswith(";"):
            stmt = " ".join(current).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []
    if current:
        stmt = " ".join(current).strip()
        if stmt:
            statements.append(stmt)
    return statements


def run():
    if not is_configured():
        print("MYSQL_* 未配置，跳过迁移。", file=sys.stderr)
        return 0
    if not MIGRATIONS_DIR.is_dir():
        print("未找到 scripts/migrations 目录。", file=sys.stderr)
        return 1
    files = sorted(f for f in MIGRATIONS_DIR.glob("*.sql") if f.is_file())
    if not files:
        print("无迁移文件。", file=sys.stderr)
        return 0
    with get_connection() as conn:
        if conn is None:
            print("无法获取 MySQL 连接。", file=sys.stderr)
            return 1
        cursor = conn.cursor()
        try:
            cursor.execute(SCHEMA_MIGRATIONS_TABLE)
            conn.commit()
        except Exception as e:
            print(f"创建 schema_migrations 表失败: {e}", file=sys.stderr)
            return 1
        for path in files:
            version = _version_from_name(path.name)
            if not version:
                continue
            cursor.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
            if cursor.fetchone():
                print(f"已应用: {path.name}")
                continue
            content = path.read_text(encoding="utf-8")
            statements = _split_sql(content)
            for stmt in statements:
                if not stmt:
                    continue
                try:
                    cursor.execute(stmt)
                except Exception as e:
                    print(f"执行失败 [{path.name}]: {e}", file=sys.stderr)
                    print(f"语句: {stmt[:200]}...", file=sys.stderr)
                    conn.rollback()
                    return 1
            cursor.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (version, path.name),
            )
            conn.commit()
            print(f"已应用: {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
