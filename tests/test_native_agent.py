# -*- coding: utf-8 -*-
"""T6 (#24)：原生 ReActAgent 装配 + M1-M5 安全机制端到端验证（agent 级 seam）。

测试 seam（spec #18）：脚本化假 ``ChatModelBase`` + 桩取数工具，不打真实 LLM/akshare。
对照 ``docs/migration/fence2-safety-checklist.md`` SI-1~12 逐条验证 M1-M5 原生落位。

运行：cd backend && python -m pytest ../tests/test_native_agent.py -c pyproject.toml -v
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from agentscope.credential import OpenAICredential
from agentscope.message import TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason, OpenAIChatModel
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionRule,
)
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

from agents.native_agent.assembly import build_fund_agent
from agents.tools.fund_tools import build_fund_permission_context


# ---------------------------------------------------------------------------
# 假 ChatModelBase：按脚本顺序返回 ChatResponse（tool_call 或文本）
# ---------------------------------------------------------------------------
class ScriptedChatModel(ChatModelBase):
    """按 ``responses`` 顺序返回的假模型。记录每次收到的 messages（供断言错误回灌）。

    ``stream=True`` 与生产 GatewayChatModel 一致；``_call_api`` 返回单个
    ``ChatResponse``（非 generator），agent 兼容此形态（见 e3 原型 _StubChatModel）。
    """

    def __init__(self, responses: list[ChatResponse]) -> None:
        super().__init__(
            credential=OpenAICredential(api_key="stub", base_url="stub"),
            model="stub-model",
            parameters=OpenAIChatModel.Parameters(),
            stream=True,
            max_retries=0,
        )
        self._responses = list(responses)
        self.call_count = 0
        self.received_messages: list[list[Any]] = []
        self.received_tools: list[list[dict] | None] = []

    async def _call_api(
        self,
        model_name: str,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse:
        self.received_messages.append(list(messages))
        self.received_tools.append(tools)
        idx = min(self.call_count, len(self._responses) - 1)
        resp = self._responses[idx]
        self.call_count += 1
        # 真实模型每次生成唯一 tool_call id；stub 复用固定 id 会被 agent 按 id 去重
        # （同 id 的后续 tool_call 不执行），故每次返回分配新鲜 id。
        fresh_blocks: list[Any] = []
        for b in resp.content or []:
            if isinstance(b, ToolCallBlock):
                fresh_blocks.append(
                    ToolCallBlock(
                        id=f"call_{self.call_count}_{b.id}",
                        name=b.name,
                        input=b.input,
                    )
                )
            else:
                fresh_blocks.append(b)
        return ChatResponse(
            content=fresh_blocks,
            is_last=resp.is_last,
            finished_reason=resp.finished_reason,
        )


def _tool_call(name: str, args: dict, call_id: str = "c1") -> ChatResponse:
    return ChatResponse(
        content=[ToolCallBlock(id=call_id, name=name, input=json.dumps(args, ensure_ascii=False))],
        is_last=True,
        finished_reason=FinishedReason.COMPLETED,
    )


def _multi_tool_call(calls: list[tuple[str, dict]]) -> ChatResponse:
    blocks = [
        ToolCallBlock(id=f"c{i}", name=n, input=json.dumps(a, ensure_ascii=False))
        for i, (n, a) in enumerate(calls)
    ]
    return ChatResponse(content=blocks, is_last=True, finished_reason=FinishedReason.COMPLETED)


def _tool_call_raw(name: str, raw_input: str, call_id: str = "c1") -> ChatResponse:
    """构造 input 为原始字符串（非合法 JSON）的 tool_call（SI-4/5 容错解析用）。"""
    return ChatResponse(
        content=[ToolCallBlock(id=call_id, name=name, input=raw_input)],
        is_last=True,
        finished_reason=FinishedReason.COMPLETED,
    )


def _text(text: str) -> ChatResponse:
    return ChatResponse(
        content=[TextBlock(text=text)],
        is_last=True,
        finished_reason=FinishedReason.COMPLETED,
    )


# ---------------------------------------------------------------------------
# 桩取数工具 + toolkit/permission（不打 akshare/Milvus）
# ---------------------------------------------------------------------------
# 桩工具用**真实工具名**（query_fund_detail / query_fund_rank / resolve_fund_code /
# query_knowledge_base），配合 T5 真实 ``build_fund_permission_context``（4 条 ALLOW），
# 顺带验证 ALLOW 规则与工具名匹配（M3）。impl 函数仅控制返回 payload。
async def _detail_single_impl(question: str) -> str:
    """查询基金详情数据。"""
    return json.dumps(
        {"payload": {"ok": True, "funds": [{"symbol": "005827"}]}},
        ensure_ascii=False,
    )


async def _detail_multi_impl(question: str) -> str:
    """查询基金详情数据。"""
    return json.dumps(
        {"payload": {"ok": True, "funds": [{"symbol": "005827"}, {"symbol": "161725"}]}},
        ensure_ascii=False,
    )


async def _rank_impl(question: str) -> str:
    """查询基金榜单/排行数据。"""
    return json.dumps(
        {"ok": True, "funds": [{"symbol": "005827"}, {"symbol": "161725"}]},
        ensure_ascii=False,
    )


async def _fail_impl(question: str) -> str:
    """查询基金详情数据。"""
    raise RuntimeError("stub boom")


def _named_tool(impl: Any, name: str) -> FunctionTool:
    """把桩 impl 包成具名只读 FunctionTool（name=真实工具名）。"""
    return FunctionTool(impl, name=name, is_read_only=True)


def _stub_toolkit(specs: list[tuple[Any, str]]) -> Toolkit:
    """specs: [(impl, tool_name), ...] -> Toolkit（basic 组）。"""
    return Toolkit(tools=[_named_tool(impl, name) for impl, name in specs])


def _stub_state(tool_names: list[str]) -> AgentState:
    """带桩 ALLOW 规则的 AgentState（4 只读工具放行，危险集暂空）。"""
    return AgentState(permission_context=_stub_permission_context(tool_names))


def _ask(msg: str) -> UserMsg:
    return UserMsg(name="user", content=[TextBlock(text=msg)])


# ---------------------------------------------------------------------------
# Smoke：装配 + 单工具调用 + 最终文本 + collector
# ---------------------------------------------------------------------------
async def test_smoke_single_fund_detail_collects_and_builds_single() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    # 真实 T5 permission_context（4 ALLOW）--顺带验证规则与工具名匹配（M3）
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("这是单只基金分析文本。"),
        ]
    )
    agent, collector = build_fund_agent(
        model=model, toolkit=toolkit, state=state
    )
    final = await agent.reply(_ask("查一下 005827"))
    final_text = "".join(
        getattr(b, "text", "") for b in (final.content or []) if hasattr(b, "text")
    )
    assert "单只基金分析文本" in final_text
    # collector 攥到了 detail payload
    assert [c.tool_name for c in collector.captured] == ["query_fund_detail"]
    out = collector.build_structured_output(final_text)
    assert out is not None
    assert out["mode"] == "single"
    assert out["text"] == final_text


# ---------------------------------------------------------------------------
# 辅助：事件收集 / 文本提取
# ---------------------------------------------------------------------------
async def _stream_events(agent: Any, msg: UserMsg) -> list[Any]:
    events: list[Any] = []
    async for ev in agent.reply_stream(msg):
        events.append(ev)
    return events


def _all_text(obj: Any) -> str:
    """递归提取所有文本（含 ToolResultBlock.output / ToolCallBlock.input 嵌套）。"""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif hasattr(obj, "text") and isinstance(getattr(obj, "text", None), str):
        out.append(obj.text)
    if isinstance(obj, list):
        for x in obj:
            out.append(_all_text(x))
    for attr in ("content", "output", "input"):
        v = getattr(obj, attr, None)
        if v is not None:
            out.append(_all_text(v))
    return "\n".join(t for t in out if t)


def _call_text(model: ScriptedChatModel, call_idx: int) -> str:
    """第 call_idx 次模型调用收到的全部文本（供错误回灌断言）。"""
    if call_idx >= len(model.received_messages):
        return ""
    return "\n".join(_all_text(m) for m in model.received_messages[call_idx])


def _final_text(msg: Any) -> str:
    return "".join(
        getattr(b, "text", "") for b in (msg.content or []) if hasattr(b, "text")
    )


# ---------------------------------------------------------------------------
# M3：4 只读工具 ALLOW 放行、危险集暂空（SI-1 部分 / M3）
# ---------------------------------------------------------------------------
def test_m3_permission_context_four_allow_rules_and_empty_dangerous_set() -> None:
    """T5 build_fund_permission_context：4 条 ALLOW（4 只读工具）、ask_rules 空（危险集暂空）。"""
    ctx = build_fund_permission_context()
    # 4 个只读工具各有一条 ALLOW 规则
    allow = ctx.allow_rules
    assert set(allow.keys()) == {
        "query_fund_rank",
        "query_fund_detail",
        "resolve_fund_code",
        "query_knowledge_base",
    }
    for rules in allow.values():
        assert all(r.behavior == PermissionBehavior.ALLOW for r in rules)
    # 危险集暂空：无 ASK 规则（M3 休眠待命）
    assert ctx.ask_rules == {}
    assert ctx.deny_rules == {}


async def test_m3_allow_tool_executes_without_hitl_pause() -> None:
    """ALLOW 规则放行：query_fund_detail 执行不触发 RequireUserConfirmEvent。"""
    from agentscope.event import RequireUserConfirmEvent

    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("分析完成。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    events = await _stream_events(agent, _ask("查 005827"))
    assert not any(isinstance(e, RequireUserConfirmEvent) for e in events)
    # 工具确实执行（collector 攥到结果）
    assert [c.tool_name for c in collector.captured] == ["query_fund_detail"]


# ---------------------------------------------------------------------------
# M2：非白名单工具被 check_tool_available 拒（SI-1 / M2）
# ---------------------------------------------------------------------------
async def test_m2_non_whitelist_tool_rejected_and_self_heals() -> None:
    """模型调未注册工具 delete_database -> check_tool_available 拒 -> ERROR 回灌 ->
    模型自愈改调合法工具 -> 正常完成。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("delete_database", {"sql": "drop table funds"}),
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("已分析。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("删库并查 005827"))
    # 自愈：最终回复产生
    assert "已分析" in _final_text(final)
    # 错误回灌到第 2 次调用：含坏工具名 + 拒绝信息
    fed_back = _call_text(model, 1)
    assert "delete_database" in fed_back
    # 合法工具在第 2 次调用执行（collector 攥到）
    assert [c.tool_name for c in collector.captured] == ["query_fund_detail"]


# ---------------------------------------------------------------------------
# M1：非法参数被 jsonschema.validate 拒（SI-2 / M1）
# ---------------------------------------------------------------------------
async def test_m1_missing_required_param_rejected_and_self_heals() -> None:
    """缺必填参数 question -> jsonschema.validate 拒 -> ERROR 回灌 -> 自愈。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {}),  # 缺 question
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("分析完成。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("查 005827"))
    assert "分析完成" in _final_text(final)
    # 错误回灌含参数校验信息 + 工具名
    fed_back = _call_text(model, 1)
    assert "query_fund_detail" in fed_back
    assert "question" in fed_back or "required" in fed_back.lower() or "validation" in fed_back.lower()
    # 合法调用执行
    assert [c.tool_name for c in collector.captured] == ["query_fund_detail"]


async def test_m1_wrong_type_param_rejected_and_self_heals() -> None:
    """参数类型错（question 传 int）-> jsonschema.validate 拒 -> ERROR 回灌 -> 自愈。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": 123}),  # 类型错
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("分析完成。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("查 005827"))
    assert "分析完成" in _final_text(final)
    # 错误回灌（第 2 次调用见到了校验失败）
    assert "query_fund_detail" in _call_text(model, 1)


# ---------------------------------------------------------------------------
# M4：无效 tool_call ERROR 回灌自愈 + max_iters 耗尽触发 ExceedMaxItersEvent
#                           （SI-4/5/7 / M4）
# ---------------------------------------------------------------------------
async def test_m4_self_heal_after_invalid_tool_call() -> None:
    """无效 tool_call（非白名单）ERROR 回灌，模型自愈后正常完成（覆盖 SI-4/6 自愈）。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("nonexistent_tool", {"x": 1}),
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("已自愈并完成。"),
        ]
    )
    agent, _ = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("查 005827"))
    assert "已自愈并完成" in _final_text(final)
    # 至少 2 次模型调用（错误回灌后重试）
    assert model.call_count >= 2


async def test_m4_exceed_max_iters_emits_event() -> None:
    """模型持续发非白名单 tool_call -> max_iters 耗尽 -> ExceedMaxItersEvent（SI-7）。"""
    from agentscope.event import ExceedMaxItersEvent

    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    # 始终发非白名单工具调用（永不给最终文本）
    model = ScriptedChatModel([_tool_call("delete_database", {"sql": "x"})])
    agent, _ = build_fund_agent(
        model=model, toolkit=toolkit, state=state, max_iters=2
    )
    events = await _stream_events(agent, _ask("删库"))
    assert any(isinstance(e, ExceedMaxItersEvent) for e in events)


# ---------------------------------------------------------------------------
# M5：多工具并发单失败被隔离，每工具独立 ToolResponse（SI-9 / M5）
# ---------------------------------------------------------------------------
async def test_m5_concurrent_tools_single_failure_isolated() -> None:
    """一轮多工具调用：query_fund_detail 成功、query_knowledge_base 失败 ->
    合法结果保留、失败独立反馈（return_exceptions=True）。"""
    toolkit = _stub_toolkit(
        [
            (_detail_single_impl, "query_fund_detail"),
            (_fail_impl, "query_knowledge_base"),
        ]
    )
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _multi_tool_call(
                [
                    ("query_fund_detail", {"question": "005827"}),
                    ("query_knowledge_base", {"question": "定投"}),
                ]
            ),
            _text("已分析（部分工具失败已隔离）。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("查 005827 并问定投"))
    # agent 未崩溃、产生最终回复
    assert "已分析" in _final_text(final)
    # 合法工具结果保留（collector 只攥 SUCCESS）
    assert "query_fund_detail" in [c.tool_name for c in collector.captured]
    # 失败工具的错误独立回灌到第 2 次调用（与成功结果并存）
    fed_back = _call_text(model, 1)
    assert "stub boom" in fed_back  # 失败反馈
    assert "005827" in fed_back  # 成功结果同时保留


# ---------------------------------------------------------------------------
# structured_outputs collector：单只/榜单 -> single、多只 -> compare（SI-12 接线）
# ---------------------------------------------------------------------------
async def test_collector_compare_mode_for_two_funds() -> None:
    toolkit = _stub_toolkit([(_detail_multi_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827 和 161725 对比"}),
            _text("对比分析文本。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("对比 005827 和 161725"))
    out = collector.build_structured_output(_final_text(final))
    assert out is not None
    assert out["mode"] == "compare"
    assert out["text"] == _final_text(final)


async def test_collector_single_mode_for_rank_list() -> None:
    toolkit = _stub_toolkit([(_rank_impl, "query_fund_rank")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_rank", {"question": "近一月涨幅前5"}),
            _text("榜单短版文本。"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("近一月涨幅前5"))
    out = collector.build_structured_output(_final_text(final))
    assert out is not None
    assert out["mode"] == "single"  # 榜单 -> single（非 compare）
    assert out["text"] == _final_text(final)


# ---------------------------------------------------------------------------
# SI-4 / SI-5：不可解析触发重试 / 可救活格式容错（M4 容错解析层）
# ---------------------------------------------------------------------------
async def test_si5_repairable_json_does_not_consume_retry() -> None:
    """SI-5：可救活格式（多余 ``}`` / 截断 / 尾逗号）被 ``_json_loads_with_repair``
    容错修复 -> 工具执行，不触发重试（不计入重试预算）。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call_raw("query_fund_detail", '{"question": "005827"}}'),  # 多余 }
            _text("done"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    await agent.reply(_ask("查 005827"))
    # 容错修复成功 -> 工具执行（被 collector 攥到）
    assert "query_fund_detail" in [c.tool_name for c in collector.captured]
    # 未触发重试：仅 2 次模型调用（tool_call + 最终文本）
    assert model.call_count == 2


async def test_si4_unparseable_input_rejected_and_self_heals() -> None:
    """SI-4：不可解析 tool_call（纯文本）不静默通过 -> 拒绝回灌 -> 模型自愈。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call_raw("query_fund_detail", "not json at all"),  # 不可解析
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("done"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    final = await agent.reply(_ask("查 005827"))
    # 不可解析调用被拒（未执行）；自愈后合法调用执行
    assert "query_fund_detail" in [c.tool_name for c in collector.captured]
    assert model.call_count >= 2  # 错误回灌后重试
    assert "done" in _final_text(final)


# ---------------------------------------------------------------------------
# SI-3：一轮多非法 tool_call 各自独立拒绝、错误一次回灌（非短路）
# ---------------------------------------------------------------------------
async def test_si3_multi_invalid_tool_calls_all_errors_fed_back() -> None:
    """SI-3：一轮内 2 个非法 tool_call（非白名单 + 缺参）各自被拒，
    两个错误都回灌到下一轮（非短路，一次收集）。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _multi_tool_call(
                [
                    ("delete_database", {"sql": "x"}),  # 非白名单
                    ("query_fund_detail", {}),  # 缺参
                ]
            ),
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("done"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    await agent.reply(_ask("查 005827"))
    # 两个错误都回灌到第 2 次调用（非短路：两个坏工具名都在反馈里）
    fed_back = _call_text(model, 1)
    assert "delete_database" in fed_back
    assert "query_fund_detail" in fed_back
    # 自愈后合法调用执行
    assert "query_fund_detail" in [c.tool_name for c in collector.captured]


# ---------------------------------------------------------------------------
# SI-6：重试反馈三要素（错误定位 + 白名单 + 修正）
# ---------------------------------------------------------------------------
async def test_si6_feedback_carries_error_location_and_whitelist() -> None:
    """SI-6 三要素：① 错误定位（原生 error text 含坏工具名，见 test_m1/m2）；
    ② 合法工具白名单随每次调用下发（tools schema）；③ 修正=模型自愈（见 test_m1/m2）。

    本测断言 ②：每次模型调用都收到 tools schema（白名单可见），错误回灌后模型
    据此选合法工具自愈。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("delete_database", {"sql": "x"}),  # 错误 -> 回灌
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("done"),
        ]
    )
    agent, collector = build_fund_agent(model=model, toolkit=toolkit, state=state)
    await agent.reply(_ask("查 005827"))
    # 每次调用都下发了 tools schema（白名单随送），非空且含合法工具
    assert len(model.received_tools) >= 2
    for tools in model.received_tools:
        assert tools, "tools schema（白名单）应随每次调用下发"
    # 自愈成功（合法工具被选中执行）
    assert "query_fund_detail" in [c.tool_name for c in collector.captured]


# ---------------------------------------------------------------------------
# SI-10：重试不修改输入对话历史
# ---------------------------------------------------------------------------
async def test_si10_retry_does_not_mutate_input_messages() -> None:
    """SI-10：错误回灌追加到 agent 内部上下文副本，不原地修改传入的输入 Msg。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    state = AgentState(permission_context=build_fund_permission_context())
    model = ScriptedChatModel(
        [
            _tool_call("delete_database", {"sql": "x"}),  # 错误 -> 回灌
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("done"),
        ]
    )
    agent, _ = build_fund_agent(model=model, toolkit=toolkit, state=state)
    user_msg = _ask("查 005827")
    snapshot = list(user_msg.content)
    await agent.reply(user_msg)
    # 输入 Msg 的 content 未被原地修改
    assert user_msg.content == snapshot
