# -*- coding: utf-8 -*-
"""
ADR-0003 决策 3+4（#42）：退役 ``agent_profiles.system_prompt`` 列 + 管理 UI prompt 编辑器。

旧链路 prompt 权威源在 DB（``system_prompt`` LONGTEXT，UI 可编辑，运行时 override）；
ADR-0003 把权威源迁到 git 文件库（``agents/prompts/*.md``），DB 列与 UI 编辑器退役。

本文件把 #42 的验收条件编码成可执行规约（retirement guard）：

- ``init.sql`` 的 ``agent_profiles`` 表无 ``system_prompt`` 列（验收 #1）。
- ``AgentUpsertBody`` API 契约无 ``system_prompt`` 字段（验收 #3）。
- ``agent_store`` 读路径（``get_agent`` / ``list_agents``）返回 dict 不含 ``system_prompt``
  且删列后 SELECT 索引重映射正确（验收 #4 + 防列错位回归）。
- ``agent_store`` 写路径（``upsert_agent``）INSERT/UPDATE SQL 不含 ``system_prompt``（验收 #4）。

测试 seam：``agent_store`` 公共函数 + ``init.sql``/``AgentUpsertBody`` 公共契约；
DB 协作者用 monkeypatch 替换为脚本化假连接（不打真实 MySQL）。

运行：cd backend && python -m pytest ../tests/test_agent_store_system_prompt_retired.py -c pyproject.toml -v
"""
from __future__ import annotations

import pathlib
from contextlib import contextmanager
from typing import Any

import pytest

from agents import agent_store


# ---------------------------------------------------------------------------
# 公共契约：init.sql 的 agent_profiles 表无 system_prompt 列（验收 #1）
# ---------------------------------------------------------------------------
def test_init_sql_agent_profiles_has_no_system_prompt_column() -> None:
    """schema 规约：agent_profiles 建表语句不得再含 system_prompt 列。"""
    init_sql = pathlib.Path(__file__).resolve().parents[1] / "cloudrun" / "mysql" / "init.sql"
    text = init_sql.read_text(encoding="utf-8")
    start = text.index("CREATE TABLE IF NOT EXISTS `agent_profiles`")
    block = text[start:]
    block = block[: block.index(") ENGINE=InnoDB")]
    assert "system_prompt" not in block, (
        "agent_profiles 建表语句仍含 system_prompt 列（ADR-0003 决策 4 要求 DROP）"
    )


# ---------------------------------------------------------------------------
# 公共契约：AgentUpsertBody API 契约无 system_prompt 字段（验收 #3）
# ---------------------------------------------------------------------------
def test_agent_upsert_body_has_no_system_prompt_field() -> None:
    """API 规约：管理端 upsert body 不再接受 system_prompt（UI 编辑器已移除）。"""
    from api.routes.agents import AgentUpsertBody

    assert "system_prompt" not in AgentUpsertBody.model_fields, (
        "AgentUpsertBody 仍声明 system_prompt 字段（ADR-0003 决策 3 要求移除 UI prompt 编辑器）"
    )


# ---------------------------------------------------------------------------
# 假 DB 协作者：脚本化连接/游标，记录被执行的 SQL 与参数
# ---------------------------------------------------------------------------
class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def execute(self, sql: str, args: object = None) -> None:
        self._conn.executed.append((sql, args))

    def fetchall(self) -> list[tuple]:
        return self._conn.fetchall_rows

    def fetchone(self) -> tuple | None:
        return self._conn.fetchone_row


class _FakeConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.fetchone_row: tuple | None = None
        self.fetchall_rows: list[tuple] = []

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        pass


def _fake_get_connection(conn: _FakeConn):
    @contextmanager
    def _cm(**_kwargs: object):
        yield conn

    return _cm


@pytest.fixture(autouse=True)
def _isolated_agent_store(monkeypatch: pytest.MonkeyPatch) -> _FakeConn:
    """每个用例：清缓存 + 装假 MySQL（已配置、返回脚本化连接）。"""
    agent_store._cache_invalidate()
    monkeypatch.setattr(agent_store, "mysql_configured", lambda: True)
    conn = _FakeConn()
    monkeypatch.setattr(agent_store, "get_connection", _fake_get_connection(conn))
    return conn


# 删列后 SELECT 的列序（9 列，无 system_prompt）：
# agent_key, name, type, enabled, skill_keys, model_id, updated_by, updated_at, deleted_at
_ROW = (
    "product_query",      # agent_key
    "产品查询",            # name
    "builtin",            # type
    1,                     # enabled
    '["rank_list"]',       # skill_keys
    7,                     # model_id
    "admin",               # updated_by
    "2026-07-27 10:00:00", # updated_at
    None,                  # deleted_at
)


# ---------------------------------------------------------------------------
# 读路径：get_agent 返回 dict 不含 system_prompt 且列映射正确（验收 #4 + 防错位）
# ---------------------------------------------------------------------------
def test_get_agent_omits_system_prompt_and_maps_columns(_isolated_agent_store: _FakeConn) -> None:
    """删列后 SELECT 索引重映射：skill_keys/model_id 落在正确位置，无 system_prompt 键。"""
    _isolated_agent_store.fetchone_row = _ROW
    obj = agent_store.get_agent("product_query")

    assert obj is not None
    assert "system_prompt" not in obj, "get_agent 返回 dict 仍带 system_prompt（列应已退役）"
    # 防列错位：删 system_prompt 后 r[4]=skill_keys、r[5]=model_id（旧 r[4]=system_prompt）
    assert obj["agent_key"] == "product_query"
    assert obj["skill_keys"] == '["rank_list"]'
    assert obj["model_id"] == 7


def test_list_agents_omits_system_prompt(_isolated_agent_store: _FakeConn) -> None:
    """list_agents 返回的每条都不含 system_prompt。"""
    _isolated_agent_store.fetchall_rows = [_ROW]
    items = agent_store.list_agents()

    assert items and len(items) == 1
    assert "system_prompt" not in items[0]
    assert items[0]["skill_keys"] == '["rank_list"]'
    assert items[0]["model_id"] == 7


# ---------------------------------------------------------------------------
# 写路径：upsert_agent 的 INSERT/UPDATE SQL 不含 system_prompt（验收 #4）
# ---------------------------------------------------------------------------
def test_upsert_agent_sql_omits_system_prompt(_isolated_agent_store: _FakeConn) -> None:
    """upsert 写入的 SQL 不得读写 system_prompt 列。"""
    ok = agent_store.upsert_agent(
        {
            "agent_key": "custom_x",
            "name": "X",
            "type": "custom",
            "enabled": True,
            "skill_keys": ["rank_list"],
            "model_id": 7,
        },
        actor_user_id="admin",
    )
    assert ok

    inserts = [(sql, args) for (sql, args) in _isolated_agent_store.executed if "INSERT" in sql]
    assert inserts, "upsert_agent 未执行 INSERT"
    sql, args = inserts[0]
    assert "system_prompt" not in sql.lower(), "INSERT SQL 仍引用 system_prompt 列"
    # 列数与参数数一致：9 列中 deleted_at 为字面 NULL，其余 8 个 %s -> 8 个参数
    assert isinstance(args, tuple) and len(args) == 8, (
        f"INSERT 参数数应为 8（删 system_prompt 后），实际 {len(args) if isinstance(args, tuple) else args}"
    )
