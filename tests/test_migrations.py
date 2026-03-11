"""迁移脚本解析与“未配置时跳过”行为。"""
import sys
from pathlib import Path

import pytest

# 项目根加入 path 以便 import scripts.run_migrations
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_migrations import _split_sql, _version_from_name


def test_version_from_name():
    assert _version_from_name("001_initial_mysql_tables.sql") == "001"
    assert _version_from_name("002_add_foo.sql") == "002"
    assert _version_from_name("no_number.sql") is None


def test_split_sql_ignores_comments_and_empty():
    sql = """
-- comment
CREATE TABLE t (id INT);

-- another
CREATE TABLE s (id INT);
"""
    stmts = _split_sql(sql)
    assert len(stmts) == 2
    assert "CREATE TABLE t" in stmts[0]
    assert "CREATE TABLE s" in stmts[1]


def test_split_sql_multiline_statement():
    sql = """
CREATE TABLE sessions (
  id VARCHAR(64) NOT NULL PRIMARY KEY
);
"""
    stmts = _split_sql(sql)
    assert len(stmts) == 1
    assert "sessions" in stmts[0] and "id" in stmts[0]


def test_run_returns_zero_when_mysql_not_configured(monkeypatch):
    from scripts import run_migrations
    monkeypatch.setattr(run_migrations, "is_configured", lambda: False)
    assert run_migrations.run() == 0


def test_003_domain_models_migration_parses_four_tables():
    """T004b: 003 迁移应包含 domain_models、domain_model_fields、data_sources、mapping_rules 四张表。"""
    migrations_dir = ROOT / "scripts" / "migrations"
    path = migrations_dir / "003_domain_models_and_data_sources.sql"
    if not path.exists():
        pytest.skip("003 migration not present")
    content = path.read_text(encoding="utf-8")
    stmts = _split_sql(content)
    create_tables = [s for s in stmts if "CREATE TABLE" in s]
    assert len(create_tables) == 4
    tables = {"domain_models", "domain_model_fields", "data_sources", "mapping_rules"}
    found = set()
    for s in create_tables:
        for t in tables:
            if t in s:
                found.add(t)
                break
    assert found == tables
