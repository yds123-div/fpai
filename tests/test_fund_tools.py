# -*- coding: utf-8 -*-
"""T5（#23）：颗粒化取数 FunctionTool 单测。

测试路径说明：backend/pyproject.toml 配置 testpaths=["../tests"]、pythonpath=["."]、
asyncio_mode="auto"。运行：cd backend && python -m pytest ../tests/test_fund_tools.py -c pyproject.toml -v

覆盖验收（#23）：
- 4 个只读工具注册为 FunctionTool，input_schema 自动抽取正确；
- 名称转代码工具对 raw code 做可信校验（臆测代码被拒 raise AgentOrientedException、可信代码放行）；
- 4 只读工具 PermissionRule(ALLOW) 生效（不触发 ASK 暂停），且裸工具默认 ASK（对照）；
- 工具只取数不调 LLM（kb 走 retrieve 不走 generate_answer；榜单/详情委托只取数 skill）。
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from agents.skills import fund_code_registry as registry
from agents.skills.fund_code_registry import FundRecord, clear_cache
from agents.tools.fund_tools import (
    FUND_TOOL_NAMES,
    build_fund_function_tools,
    build_fund_permission_context,
    build_fund_permission_rules,
    build_fund_toolkit,
    query_fund_detail,
    query_fund_rank,
    query_knowledge_base,
    resolve_fund_code,
)
from agentscope.exception import AgentOrientedException
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionEngine,
)

# 与 test_fund_code_registry.py 一致的确定性测试数据（不触网）
TEST_FUNDS: list[FundRecord] = [
    FundRecord(code="005827", name="易方达蓝筹精选混合", type="混合型"),
    FundRecord(code="161725", name="招商中证白酒指数", type="指数型"),
    FundRecord(code="110011", name="易方达优质精选混合", type="混合型"),
    FundRecord(code="005876", name="易方达蓝筹精选混合C", type="混合型"),
]


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """注入确定性基金列表到 registry 缓存，用完清空。"""
    monkeypatch.setattr(registry, "_load_fund_list", lambda: TEST_FUNDS)
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# 验收 2/5：名称转代码工具对 raw code 做可信校验
# ---------------------------------------------------------------------------
async def test_resolve_trusted_code_returns_record(seeded: None) -> None:
    """可信代码 -> 放行并返回可信记录（取数成功）。"""
    out = json.loads(await resolve_fund_code("005827"))
    assert out["ok"] is True
    assert out["mode"] == "code_provided"
    assert len(out["codes"]) == 1
    assert out["codes"][0]["code"] == "005827"
    assert out["codes"][0]["name"] == "易方达蓝筹精选混合"
    assert out["codes"][0]["type"] == "混合型"


async def test_resolve_speculative_code_rejected(seeded: None) -> None:
    """臆测 6 位代码不在可信集 -> 工具内自校验拒绝（raise AgentOrientedException）。"""
    with pytest.raises(AgentOrientedException):
        await resolve_fund_code("999999")


async def test_resolve_mixed_codes_rejected_if_any_speculative(seeded: None) -> None:
    """可信 + 臆测混合：任一臆测即拒绝整次调用（不部分放行臆测代码）。"""
    with pytest.raises(AgentOrientedException):
        await resolve_fund_code("005827 和 999999 对比")


async def test_resolve_multiple_trusted_codes_all_pass(seeded: None) -> None:
    """多个可信代码 -> 全部放行。"""
    out = json.loads(await resolve_fund_code("005827 161725"))
    assert out["ok"] is True
    assert out["mode"] == "code_provided"
    codes = {c["code"] for c in out["codes"]}
    assert codes == {"005827", "161725"}


async def test_resolve_code_strips_whitespace(seeded: None) -> None:
    """去空白后仍是可信代码 -> 放行。"""
    out = json.loads(await resolve_fund_code("  005827  "))
    assert out["ok"] is True
    assert out["codes"][0]["code"] == "005827"


async def test_resolve_name_returns_matches(seeded: None) -> None:
    """名称查询 -> registry.resolve 多策略命中。"""
    out = json.loads(await resolve_fund_code("易方达蓝筹精选"))
    assert out["ok"] is True
    assert out["mode"] == "name_to_code"
    codes = {m["code"] for m in out["matches"]}
    assert "005827" in codes


async def test_resolve_name_no_match_aborts(seeded: None) -> None:
    """名称未命中可信集 -> 中止回灌自愈（raise AgentOrientedException）。"""
    with pytest.raises(AgentOrientedException):
        await resolve_fund_code("完全不存在的基金XYZ")


async def test_resolve_empty_input_aborts(seeded: None) -> None:
    """空输入 -> 中止（不给模型留采纳空查询的余地）。"""
    with pytest.raises(AgentOrientedException):
        await resolve_fund_code("")


# ---------------------------------------------------------------------------
# 验收 1：4 个只读工具注册为 FunctionTool，input_schema 自动抽取正确
# ---------------------------------------------------------------------------
def test_build_function_tools_registers_four_readonly_tools() -> None:
    tools = build_fund_function_tools()
    assert len(tools) == 4
    assert {t.name for t in tools} == set(FUND_TOOL_NAMES)
    for t in tools:
        assert t.is_read_only is True
        assert t.description, f"{t.name} 描述应从 docstring 自动抽取"
        assert t.input_schema is not None
        assert t.input_schema.get("type") == "object"
        assert "properties" in t.input_schema


def test_input_schema_auto_extracted_from_signature() -> None:
    """input_schema 由签名 + docstring 自动抽取：必填/可选、参数名、描述。"""
    tools = {t.name: t for t in build_fund_function_tools()}

    # query_fund_rank / query_fund_detail / resolve_fund_code：单个必填参数
    for name, param in [
        ("query_fund_rank", "question"),
        ("query_fund_detail", "question"),
        ("resolve_fund_code", "query"),
    ]:
        schema = tools[name].input_schema
        assert param in schema["properties"], f"{name} 缺参数 {param}"
        assert param in schema.get("required", []), f"{name}.{param} 应必填"
        # docstring 描述应被抽取进 schema
        assert schema["properties"][param].get("description"), (
            f"{name}.{param} 描述未从 docstring 抽取"
        )

    # query_knowledge_base：question 必填 + top_k 可选（默认 10）
    schema_kb = tools["query_knowledge_base"].input_schema
    assert "question" in schema_kb["properties"]
    assert "top_k" in schema_kb["properties"]
    assert "question" in schema_kb.get("required", [])
    assert "top_k" not in schema_kb.get("required", []), "top_k 有默认值，应可选"


def test_build_toolkit_registers_four_tools_in_basic_group() -> None:
    """Toolkit 把 4 个工具放入 'basic' 组（始终激活的白名单）。"""
    tk = build_fund_toolkit()
    basic = next(g for g in tk.tool_groups if g.name == "basic")
    assert {t.name for t in basic.tools} == set(FUND_TOOL_NAMES)


# ---------------------------------------------------------------------------
# 验收 3：4 只读工具 PermissionRule(ALLOW) 生效（不触发 ASK 暂停）
# ---------------------------------------------------------------------------
def test_permission_rules_cover_four_tools() -> None:
    rules = build_fund_permission_rules()
    assert len(rules) == 4
    for r in rules:
        assert r.behavior == PermissionBehavior.ALLOW
        assert r.rule_content is None  # None = 匹配该工具所有输入
        assert r.tool_name in FUND_TOOL_NAMES
    assert {r.tool_name for r in rules} == set(FUND_TOOL_NAMES)


def test_permission_context_allow_rules_cover_four_tools() -> None:
    ctx = build_fund_permission_context()
    for name in FUND_TOOL_NAMES:
        assert name in ctx.allow_rules
        assert len(ctx.allow_rules[name]) == 1
        assert ctx.allow_rules[name][0].behavior == PermissionBehavior.ALLOW


async def test_allow_rules_grant_permission_without_ask() -> None:
    """装载 ALLOW 规则后，4 工具的权限判定均为 ALLOW（不触发 ASK 暂停）。

    直接用 PermissionEngine(ctx).check_permission 复现 Agent 内置引擎的判定路径
    （Agent.__init__ 内 self._engine = PermissionEngine(state.permission_context)）。
    """
    engine = PermissionEngine(build_fund_permission_context())
    for tool in build_fund_function_tools():
        sample = (
            {"query": "005827"}
            if tool.name == "resolve_fund_code"
            else {"question": "示例问题"}
        )
        decision = await engine.check_permission(tool, sample)
        assert decision.behavior == PermissionBehavior.ALLOW, (
            f"{tool.name} 应被 ALLOW，实际 {decision.behavior}"
        )


async def test_bare_function_tool_defaults_to_ask() -> None:
    """对照：不注册 ALLOW 规则时，FunctionTool 默认 ASK（证明需要 ALLOW 规则）。"""
    engine = PermissionEngine(PermissionContext())  # 无规则
    tool = build_fund_function_tools()[0]
    decision = await engine.check_permission(tool, {"question": "示例问题"})
    assert decision.behavior == PermissionBehavior.ASK


# ---------------------------------------------------------------------------
# 验收 4：工具只取数不调 LLM
# ---------------------------------------------------------------------------
async def test_knowledge_base_tool_uses_retrieve_not_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """kb 工具走 retrieval.service.retrieve（仅检索），不调 generate_answer（LLM）。"""
    from retrieval import service as rag_svc
    from retrieval.types import Citation, RetrieveResult

    fake = RetrieveResult(
        chunks=[{"doc_id": "d1", "source": "kb", "chunk_text": "定投开户流程"}],
        scores=[0.9],
        citations=[
            Citation(doc_id="d1", source="kb", chunk_text="定投开户流程", score=0.9),
        ],
    )
    monkeypatch.setattr(rag_svc, "retrieve", lambda **kw: fake)

    generate_calls = {"n": 0}

    def _fail_if_called(**kw: Any) -> Any:
        generate_calls["n"] += 1
        raise AssertionError("kb 工具不应调用 generate_answer（LLM 生成）")

    monkeypatch.setattr(rag_svc, "generate_answer", _fail_if_called)

    out = json.loads(await query_knowledge_base("基金定投怎么开户"))
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["chunks"][0]["doc_id"] == "d1"
    assert generate_calls["n"] == 0


async def test_knowledge_base_empty_question_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """空问题不触发检索（无意义 embed），返回 ok=False。"""
    from retrieval import service as rag_svc

    retrieve_calls = {"n": 0}

    def _should_not_be_called(**kw: Any) -> Any:
        retrieve_calls["n"] += 1
        raise AssertionError("空问题不应触发 retrieve")

    monkeypatch.setattr(rag_svc, "retrieve", _should_not_be_called)

    out = json.loads(await query_knowledge_base(""))
    assert out["ok"] is False
    assert retrieve_calls["n"] == 0


async def test_query_fund_rank_delegates_to_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    """查榜单工具委托 product_query.run（只取数 skill），原样回传其 JSON。"""
    from agents.skills.product_query import runtime as rank_rt

    captured: dict[str, Any] = {}

    async def _fake_run(question: str, ctx: dict[str, Any]) -> str:
        captured["question"] = question
        captured["ctx"] = ctx
        return json.dumps({"ok": True, "mode": "rank", "items": []}, ensure_ascii=False)

    monkeypatch.setattr(rank_rt, "run", _fake_run)

    out = json.loads(await query_fund_rank("近一月涨幅前5的基金"))
    assert out["ok"] is True
    assert out["mode"] == "rank"
    assert captured["question"] == "近一月涨幅前5的基金"
    assert captured["ctx"] == {}


async def test_query_fund_detail_delegates_to_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    """查详情工具委托 product_compare.run（只取数 skill），原样回传其 JSON。"""
    from agents.skills.product_compare import runtime as cmp_rt

    captured: dict[str, Any] = {}

    async def _fake_run(question: str, ctx: dict[str, Any]) -> str:
        captured["question"] = question
        return json.dumps({"ok": True, "symbols": ["005827"]}, ensure_ascii=False)

    monkeypatch.setattr(cmp_rt, "run", _fake_run)

    out = json.loads(await query_fund_detail("005827 的详情"))
    assert out["ok"] is True
    assert captured["question"] == "005827 的详情"
