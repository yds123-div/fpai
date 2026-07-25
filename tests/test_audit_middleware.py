# -*- coding: utf-8 -*-
"""T7 (#25)：AuditMiddleware 审计适配层（栅栏 #4）端到端验证。

测试 seam：脚本化假 ``ChatModelBase`` + 桩取数工具（复用 T6 seam 形态），
不打真实 LLM/akshare/MySQL。对照 G6/#9 六决策（D1-D6）+ #25 验收逐条验证：

- D1 混合落点：``on_reply``（主，捕 ToolResultEndEvent 全状态 + ExceedMaxItersEvent
  + 最终 Msg）+ ``on_acting``（富细节，ALLOW 工具）+ ``on_model_call``（模型异常）。
- D2 answer_id 经 contextvars 线程化。
- D3 两层事件：``tool_call``（per-occurrence，带 state）+ ``reply_outcome``
  （per-reply，outcome = first_pass[不发] / self_healed / partial / fallback）。
- D4 ``on_model_call`` 捕模型异常 -> ``model_call_error`` per-occurrence。
- D5 与 ``TracingMiddleware`` 分立两独立 middleware（双发不耦合）。
- D6 每次工具调用都记 + 去重（on_acting 记已处理 id，on_reply 跳过）+ payload 截断。

运行：cd backend && uv run pytest ../tests/test_audit_middleware.py -c pyproject.toml -v
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from agentscope.credential import OpenAICredential
from agentscope.message import TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason, OpenAIChatModel
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

from agents.native_agent.assembly import build_fund_agent
from agents.native_agent.audit_middleware import (
    AuditMiddleware,
    AuditRecord,
    get_audit_answer_id,
    reset_audit_answer_id,
    set_audit_answer_id,
)
from agents.tools.fund_tools import build_fund_permission_context


# ---------------------------------------------------------------------------
# 假 ChatModelBase：按脚本顺序返回 ChatResponse；可选在第 N 次调用抛异常
# ---------------------------------------------------------------------------
class ScriptedChatModel(ChatModelBase):
    """按 ``responses`` 顺序返回的假模型（与 T6 seam 同形态）。

    ``raise_on_call``：若不为 None，第该次（0-base）调用抛 ``exc``，用于 on_model_call。
    """

    def __init__(
        self,
        responses: list[ChatResponse],
        *,
        raise_exc: Exception | None = None,
    ) -> None:
        super().__init__(
            credential=OpenAICredential(api_key="stub", base_url="stub"),
            model="stub-model",
            parameters=OpenAIChatModel.Parameters(),
            stream=True,
            max_retries=0,
        )
        self._responses = list(responses)
        self._raise_exc = raise_exc
        self.call_count = 0

    async def _call_api(
        self,
        model_name: str,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse:
        idx = self.call_count
        self.call_count += 1
        if self._raise_exc is not None:
            raise self._raise_exc
        resp = self._responses[min(idx, len(self._responses) - 1)]
        fresh: list[Any] = []
        for b in resp.content or []:
            if isinstance(b, ToolCallBlock):
                fresh.append(
                    ToolCallBlock(
                        id=f"call_{self.call_count}_{b.id}",
                        name=b.name,
                        input=b.input,
                    )
                )
            else:
                fresh.append(b)
        return ChatResponse(
            content=fresh,
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


def _text(text: str) -> ChatResponse:
    return ChatResponse(
        content=[TextBlock(text=text)],
        is_last=True,
        finished_reason=FinishedReason.COMPLETED,
    )


# ---------------------------------------------------------------------------
# 桩取数工具 + toolkit/permission
# ---------------------------------------------------------------------------
async def _detail_single_impl(question: str) -> str:
    """查询基金详情数据。"""
    return json.dumps({"payload": {"ok": True, "funds": [{"symbol": "005827"}]}}, ensure_ascii=False)


async def _fail_impl(question: str) -> str:
    """查询基金详情数据。"""
    raise RuntimeError("stub boom")


def _named_tool(impl: Any, name: str) -> FunctionTool:
    return FunctionTool(impl, name=name, is_read_only=True)


def _stub_toolkit(specs: list[tuple[Any, str]]) -> Toolkit:
    return Toolkit(tools=[_named_tool(impl, name) for impl, name in specs])


def _state() -> AgentState:
    return AgentState(permission_context=build_fund_permission_context())


def _ask(msg: str) -> UserMsg:
    return UserMsg(name="user", content=[TextBlock(text=msg)])


def _final_text(msg: Any) -> str:
    return "".join(
        getattr(b, "text", "") for b in (msg.content or []) if hasattr(b, "text")
    )


# ---------------------------------------------------------------------------
# 辅助：跑一回合 + 取审计事件
# ---------------------------------------------------------------------------
async def _run_with_audit(
    model: ScriptedChatModel,
    *,
    toolkit: Toolkit,
    answer_id: str | None = "ans-1",
    max_iters: int = 8,
) -> tuple[Any, AuditMiddleware]:
    mw = AuditMiddleware()
    agent, _ = build_fund_agent(
        model=model, toolkit=toolkit, state=_state(), middlewares=[mw], max_iters=max_iters
    )
    token = set_audit_answer_id(answer_id) if answer_id is not None else None
    try:
        final = await agent.reply(_ask("查 005827"))
    finally:
        if token is not None:
            reset_audit_answer_id(token)
    return final, mw


def _events(mw: AuditMiddleware, event_type: str) -> list[AuditRecord]:
    return [e for e in mw.events if e.event_type == event_type]


# ---------------------------------------------------------------------------
# D3 outcome = first_pass：无 tool_call_error、无 ExceedMaxIters -> 不发 reply_outcome
# ---------------------------------------------------------------------------
async def test_first_pass_emits_no_reply_outcome() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("分析完成。")]
    )
    final, mw = await _run_with_audit(model, toolkit=toolkit)
    assert "分析完成" in _final_text(final)
    # 工具调用审计：一次 SUCCESS（D6 每次都记）
    tool_calls = _events(mw, "tool_call")
    assert len(tool_calls) == 1
    assert tool_calls[0].payload["tool_name"] == "query_fund_detail"
    assert tool_calls[0].payload["state"] == "success"
    # first_pass：无 reply_outcome 事件（D3 first_pass[不发]）
    assert _events(mw, "reply_outcome") == []
    assert _events(mw, "model_call_error") == []


# ---------------------------------------------------------------------------
# D3 outcome = self_healed：M4 校验/权限拒 -> ERROR 回灌 -> 自愈 -> 最终成功
# ---------------------------------------------------------------------------
async def test_self_healed_outcome_after_non_whitelist_error() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [
            _tool_call("delete_database", {"sql": "drop table funds"}),  # 非白名单 -> ERROR
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("已分析。"),
        ]
    )
    final, mw = await _run_with_audit(model, toolkit=toolkit)
    assert "已分析" in _final_text(final)
    # 两个 tool_call 事件：一个 ERROR（on_reply 补漏）、一个 SUCCESS（on_acting 富细节）
    tool_calls = _events(mw, "tool_call")
    states = {c.payload["tool_name"]: c.payload["state"] for c in tool_calls}
    assert states["delete_database"] == "error"
    assert states["query_fund_detail"] == "success"
    # reply_outcome = self_healed
    outcomes = _events(mw, "reply_outcome")
    assert len(outcomes) == 1
    assert outcomes[0].payload["outcome"] == "self_healed"
    assert outcomes[0].payload["error_count"] >= 1


# ---------------------------------------------------------------------------
# D3 outcome = self_healed：M1 参数校验失败 -> ERROR 回灌 -> 自愈
# （验证 on_reply 补漏 validation-ERROR，on_acting 未见过该 tool_call_id）
# ---------------------------------------------------------------------------
async def test_self_healed_outcome_after_validation_error() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {}),  # 缺必填 question -> 校验 ERROR
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("完成。"),
        ]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit)
    tool_calls = _events(mw, "tool_call")
    # 校验失败那次：on_acting 未执行 -> 无富细节（input/result 缺省），由 on_reply 捕
    val_err = [c for c in tool_calls if c.payload["state"] == "error"]
    assert len(val_err) == 1
    assert val_err[0].payload["tool_name"] == "query_fund_detail"
    assert "input" not in val_err[0].payload  # 校验失败无富细节
    outcomes = _events(mw, "reply_outcome")
    assert outcomes[0].payload["outcome"] == "self_healed"


# ---------------------------------------------------------------------------
# D3 outcome = partial：M5 批次部分工具失败（runtime ERROR 经 on_acting）
# ---------------------------------------------------------------------------
async def test_partial_outcome_after_concurrent_tool_failure() -> None:
    toolkit = _stub_toolkit(
        [(_detail_single_impl, "query_fund_detail"), (_fail_impl, "query_knowledge_base")]
    )
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
    final, mw = await _run_with_audit(model, toolkit=toolkit)
    assert "已分析" in _final_text(final)
    tool_calls = _events(mw, "tool_call")
    states = {c.payload["tool_name"]: c.payload["state"] for c in tool_calls}
    assert states["query_fund_detail"] == "success"
    assert states["query_knowledge_base"] == "error"
    # runtime ERROR 经 on_acting -> 富细节（含 input/result/latency）
    kb_err = [c for c in tool_calls if c.payload["tool_name"] == "query_knowledge_base"][0]
    assert "input" in kb_err.payload  # on_acting 富细节
    assert "latency_ms" in kb_err.payload
    outcomes = _events(mw, "reply_outcome")
    assert outcomes[0].payload["outcome"] == "partial"


# ---------------------------------------------------------------------------
# D3 outcome = fallback：max_iters 耗尽触发 ExceedMaxItersEvent
# ---------------------------------------------------------------------------
async def test_fallback_outcome_on_exceed_max_iters() -> None:
    from agentscope.event import ExceedMaxItersEvent

    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel([_tool_call("delete_database", {"sql": "x"})])
    mw = AuditMiddleware()
    agent, _ = build_fund_agent(
        model=model, toolkit=toolkit, state=_state(), middlewares=[mw], max_iters=2
    )
    token = set_audit_answer_id("ans-fb")
    events: list[Any] = []
    try:
        async for ev in agent.reply_stream(_ask("删库")):
            events.append(ev)
    finally:
        reset_audit_answer_id(token)
    assert any(isinstance(e, ExceedMaxItersEvent) for e in events)
    outcomes = _events(mw, "reply_outcome")
    assert len(outcomes) == 1
    assert outcomes[0].payload["outcome"] == "fallback"


# ---------------------------------------------------------------------------
# D6 on_acting 富细节：SUCCESS 工具事件含 input/result 摘要 + latency
# ---------------------------------------------------------------------------
async def test_on_acting_rich_detail_for_allow_tool() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit)
    tc = _events(mw, "tool_call")[0]
    assert tc.payload["state"] == "success"
    assert "005827" in tc.payload["input"]  # input 摘要
    assert "ok" in str(tc.payload["result"])  # result 摘要（payload 含 ok）
    assert isinstance(tc.payload["latency_ms"], (int, float))
    assert tc.payload["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# D6 去重：ALLOW 工具经 on_acting 已记，on_reply 跳过（不双发 tool_call）
# ---------------------------------------------------------------------------
async def test_dedup_allow_tool_not_double_emitted() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit)
    tool_calls = _events(mw, "tool_call")
    # 同名工具只一条 tool_call（on_acting 发了，on_reply 跳过）
    assert len(tool_calls) == 1


# ---------------------------------------------------------------------------
# D4 on_model_call 捕模型异常 -> model_call_error per-occurrence，异常重抛
# ---------------------------------------------------------------------------
async def test_on_model_call_captures_exception_and_outcome_fallback() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel([], raise_exc=RuntimeError("model down"))
    mw = AuditMiddleware()
    agent, _ = build_fund_agent(
        model=model, toolkit=toolkit, state=_state(), middlewares=[mw], max_iters=3
    )
    token = set_audit_answer_id("ans-m")
    try:
        with pytest.raises(Exception):
            await agent.reply(_ask("查 005827"))
    finally:
        reset_audit_answer_id(token)
    errs = _events(mw, "model_call_error")
    assert len(errs) >= 1
    assert errs[0].payload["error_type"] == "RuntimeError"
    assert "model down" in errs[0].payload["error_message"]
    # 模型耗尽 -> 回合未正常完成 -> outcome=fallback
    outcomes = _events(mw, "reply_outcome")
    assert len(outcomes) == 1
    assert outcomes[0].payload["outcome"] == "fallback"


# ---------------------------------------------------------------------------
# D2 answer_id 经 contextvars：事件携带 answer_id；无 answer_id 不发
# ---------------------------------------------------------------------------
async def test_answer_id_threaded_via_contextvars() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit, answer_id="ans-ctx-42")
    for rec in mw.events:
        assert rec.answer_id == "ans-ctx-42"


async def test_no_answer_id_emits_nothing() -> None:
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit, answer_id=None)
    assert mw.events == []  # 无 answer_id 不落审计（延续 SI-11 test 24）


def test_get_set_reset_answer_id_roundtrip() -> None:
    assert get_audit_answer_id() is None
    token = set_audit_answer_id("aid-x")
    assert get_audit_answer_id() == "aid-x"
    reset_audit_answer_id(token)
    assert get_audit_answer_id() is None


# ---------------------------------------------------------------------------
# 桥接 audit.append_event：monkeypatch spy 验证两层事件均落 append_event
# ---------------------------------------------------------------------------
async def test_append_event_bridge_called_with_two_layers(monkeypatch) -> None:
    import audit

    recorded: list[dict] = []

    def _fake_append(answer_id, event_type, payload, *, session_id=None, user_id=None, **kw):
        recorded.append(
            {"answer_id": answer_id, "event_type": event_type, "payload": payload}
        )

    monkeypatch.setattr(audit, "append_event", _fake_append)
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [
            _tool_call("delete_database", {"sql": "x"}),  # ERROR -> self_heal
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("done"),
        ]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit, answer_id="aid-bridge")
    # tool_call 层 + reply_outcome 层都经 append_event
    types = [r["event_type"] for r in recorded]
    assert "tool_call" in types
    assert "reply_outcome" in types
    for r in recorded:
        assert r["answer_id"] == "aid-bridge"
    # reply_outcome outcome 正确（self_healed）
    ro = [r for r in recorded if r["event_type"] == "reply_outcome"][0]
    assert ro["payload"]["outcome"] == "self_healed"


# ---------------------------------------------------------------------------
# D5 与 TracingMiddleware 分立两独立 middleware（双发不耦合）
# ---------------------------------------------------------------------------
async def test_coexistence_with_tracing_middleware_independent() -> None:
    from agentscope.middleware import TracingMiddleware

    audit_mw = AuditMiddleware()
    tracing_mw = TracingMiddleware()  # 无 setup_tracing -> no-op（ADR-0002 暂停）
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    agent, _ = build_fund_agent(
        model=model,
        toolkit=toolkit,
        state=_state(),
        middlewares=[tracing_mw, audit_mw],
    )
    token = set_audit_answer_id("ans-coexist")
    try:
        await agent.reply(_ask("查 005827"))
    finally:
        reset_audit_answer_id(token)
    # TracingMiddleware no-op 不影响 AuditMiddleware 独立捕获
    assert len(_events(audit_mw, "tool_call")) == 1
    assert _events(audit_mw, "reply_outcome") == []  # first_pass


# ---------------------------------------------------------------------------
# assembly 接线：build_fund_agent 默认挂 AuditMiddleware
# ---------------------------------------------------------------------------
async def test_build_fund_agent_attaches_audit_middleware_by_default() -> None:
    from agents.native_agent.audit_middleware import AuditMiddleware

    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    agent, _ = build_fund_agent(model=model, toolkit=toolkit, state=_state())
    # agent 的 reply middleware 链含 AuditMiddleware
    assert any(isinstance(m, AuditMiddleware) for m in agent._reply_middlewares)


# ---------------------------------------------------------------------------
# GET /api/v1/evidence/{answerId} 证据结构不变：emit 的事件仍是 event_type+payload
# ---------------------------------------------------------------------------
async def test_emitted_events_keep_evidence_shape() -> None:
    """证据结构 = audit_events 行（answer_id, event_type, payload）。
    AuditMiddleware 只新增 event_type（tool_call/reply_outcome/model_call_error），
    不改 get_evidence 返回的 dict 形状（下游消费方零改动）。"""
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    model = ScriptedChatModel(
        [_tool_call("query_fund_detail", {"question": "005827"}), _text("done")]
    )
    _, mw = await _run_with_audit(model, toolkit=toolkit)
    for rec in mw.events:
        # 每条事件 = (event_type:str, payload:dict)，与 audit_events 表形状一致
        assert isinstance(rec.event_type, str)
        assert isinstance(rec.payload, dict)
