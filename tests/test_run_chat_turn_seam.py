# -*- coding: utf-8 -*-
"""T10 (#28) 主 seam：``run_chat_turn_async`` 端到端结果形态验收（SI-1~12）。

吸收被删的 24 个 plan_validation 单测为端到端结果形态验收：脚本化假 ``ChatModelBase``
+ 桩取数工具 + 假 ``fund_code_registry``，不打真实 LLM/akshare/auth/Redis。只测外部行为
（回复形态 / structured_outputs / 流式契约 / 审计两层事件 / 栅栏 #1-3），不测 ReAct
内部步骤数/中间消息结构等易碎实现细节（spec #18）。

运行：cd backend && python -m pytest ../tests/test_run_chat_turn_seam.py -c pyproject.toml -v
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from agentscope.credential import OpenAICredential
from agentscope.message import TextBlock, ToolCallBlock
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason, OpenAIChatModel
from agentscope.tool import FunctionTool, Toolkit

from agents.tools.fund_tools import build_fund_permission_context
from agentscope.state import AgentState
from orchestrator.run import run_chat_turn_async


# ---------------------------------------------------------------------------
# 假 ChatModelBase：按脚本顺序返回 ChatResponse（tool_call 或文本）
# ---------------------------------------------------------------------------
class ScriptedChatModel(ChatModelBase):
    """按 ``responses`` 顺序返回的假模型；记录每次收到的 messages/tools。"""

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

    async def _call_api(
        self,
        model_name: str,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse:
        idx = min(self.call_count, len(self._responses) - 1)
        resp = self._responses[idx]
        self.call_count += 1
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


class RaisingChatModel(ScriptedChatModel):
    """永远抛异常的假模型（栅栏 #3 case A：LLM-down）。"""

    def __init__(self, exc: Exception) -> None:
        super().__init__([])
        self._exc = exc

    async def _call_api(self, *args: Any, **kwargs: Any) -> ChatResponse:
        self.call_count += 1
        raise self._exc


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


def _thinking_text(think: str, text: str) -> ChatResponse:
    """含推理块的回复（ThinkingBlock，原生分离路径）。"""
    from agentscope.message import ThinkingBlock

    return ChatResponse(
        content=[ThinkingBlock(thinking=think), TextBlock(text=text)],
        is_last=True,
        finished_reason=FinishedReason.COMPLETED,
    )


# ---------------------------------------------------------------------------
# 桩取数工具（真实工具名 + 真实 permission_context；impl 仅控制返回 payload）
# ---------------------------------------------------------------------------
async def _detail_single_impl(question: str) -> str:
    return json.dumps(
        {"payload": {"ok": True, "funds": [{"symbol": "005827"}]}},
        ensure_ascii=False,
    )


async def _detail_multi_impl(question: str) -> str:
    return json.dumps(
        {"payload": {"ok": True, "funds": [{"symbol": "005827"}, {"symbol": "161725"}]}},
        ensure_ascii=False,
    )


async def _rank_impl(question: str) -> str:
    return json.dumps(
        {"ok": True, "funds": [{"symbol": "005827"}, {"symbol": "161725"}]},
        ensure_ascii=False,
    )


async def _kb_impl(question: str, top_k: int = 10) -> str:
    return json.dumps(
        {"ok": True, "count": 1, "chunks": [{"source": "kb", "chunk_text": "定投知识片段"}]},
        ensure_ascii=False,
    )


async def _resolve_ok_impl(query: str) -> str:
    return json.dumps(
        {"ok": True, "mode": "code_provided", "codes": [{"code": "005827", "name": "易方达蓝筹"}]},
        ensure_ascii=False,
    )


def _named_tool(impl: Any, name: str) -> FunctionTool:
    return FunctionTool(impl, name=name, is_read_only=True)


def _stub_toolkit(specs: list[tuple[Any, str]]) -> Toolkit:
    return Toolkit(tools=[_named_tool(impl, name) for impl, name in specs])


def _full_stub_toolkit() -> Toolkit:
    """4 只读工具全桩（query_fund_detail/rank/resolve/kb）。"""
    return _stub_toolkit(
        [
            (_detail_single_impl, "query_fund_detail"),
            (_rank_impl, "query_fund_rank"),
            (_resolve_ok_impl, "resolve_fund_code"),
            (_kb_impl, "query_knowledge_base"),
        ]
    )


def _stub_fallback() -> Any:
    """桩 HeuristicFallback：4 工具全桩，不打 akshare/Milvus。"""
    from agents.native_agent.heuristic_fallback import HeuristicFallback

    return HeuristicFallback(
        rank_tool=_rank_impl,
        detail_tool=_detail_single_impl,
        resolve_tool=_resolve_ok_impl,
        kb_tool=_kb_impl,
    )


def _capturing_progress() -> tuple[list[tuple[str, dict]], Any]:
    """返回 (events, callback)：callback 收集 (stage, kwargs)。"""
    events: list[tuple[str, dict]] = []

    async def _cb(stage: str, **kwargs: Any) -> None:
        events.append((stage, dict(kwargs)))

    return events, _cb


def _capturing_stream() -> tuple[list[str], Any]:
    tokens: list[str] = []

    async def _cb(token: str) -> None:
        if token:
            tokens.append(token)

    return tokens, _cb


# ---------------------------------------------------------------------------
# SI-1 / SI-2 / SI-3：回复形态（单只标准 / 榜单短版 / 多只对比）
# ---------------------------------------------------------------------------
async def test_si1_single_fund_standard_reply_and_single_structured() -> None:
    """SI-1：单只基金 -> 标准回复 + structured_outputs single 模式。"""
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("这是单只基金的标准解读。"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    result = await run_chat_turn_async(
        "查一下 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    assert "标准解读" in (result.answer_blocks[0] if result.answer_blocks else "")
    assert len(result.structured_outputs) == 1
    assert result.structured_outputs[0]["mode"] == "single"
    assert result.structured_outputs[0]["text"] == result.raw_reply


async def test_si2_rank_list_short_reply_and_single_structured() -> None:
    """SI-2：榜单 -> 短版回复 + structured single（榜单非对比）。"""
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_rank", {"question": "近一月涨幅前5"}),
            _text("榜单短版回复。"),
        ]
    )
    toolkit = _stub_toolkit([(_rank_impl, "query_fund_rank")])
    result = await run_chat_turn_async(
        "近一月涨幅前5的基金",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    assert "榜单短版" in (result.answer_blocks[0] if result.answer_blocks else "")
    assert result.structured_outputs[0]["mode"] == "single"


async def test_si3_multi_fund_compare_reply_and_compare_structured() -> None:
    """SI-3：多只基金 -> 比较+优选 + structured compare 模式。"""
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827 和 161725 对比"}),
            _text("对比分析+优选建议。"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_multi_impl, "query_fund_detail")])
    result = await run_chat_turn_async(
        "对比 005827 和 161725",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    assert result.structured_outputs[0]["mode"] == "compare"


# ---------------------------------------------------------------------------
# SI-4：structured_outputs 形状（FundAnalysisOutput 关键字段）
# ---------------------------------------------------------------------------
async def test_si4_structured_output_shape() -> None:
    """SI-4：structured_outputs 含 type/mode/summary/sections/charts/text 关键字段。"""
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("【基本信息】单只分析。"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    result = await run_chat_turn_async(
        "查 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    out = result.structured_outputs[0]
    for key in ("type", "mode", "summary", "sections", "charts", "text"):
        assert key in out, f"structured_output 缺字段 {key}"
    assert out["mode"] == "single"


# ---------------------------------------------------------------------------
# SI-5：流式契约（5 核心阶段 + token 分片 + reset_tools 过滤）
# ---------------------------------------------------------------------------
async def test_si5_streaming_contract_core_stages_and_tokens() -> None:
    """SI-5：5 核心阶段命中 + token 分片经 stream_callback + reset_tools 不进 skill_fetching。"""
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("回复正文"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    prog_events, prog_cb = _capturing_progress()
    tokens, stream_cb = _capturing_stream()
    result = await run_chat_turn_async(
        "查 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
        progress_callback=prog_cb,
        stream_callback=stream_cb,
    )
    stages = [s for s, _ in prog_events]
    # 5 核心阶段（accepted/thinking/skill_fetching/llm_generating/model_first_token/done）
    for stage in ("accepted", "thinking", "skill_fetching", "llm_generating", "model_first_token", "done"):
        assert stage in stages, f"缺核心阶段 {stage}（stages={stages}）"
    # token 分片经 stream_callback
    assert "".join(tokens) == "回复正文"
    # reset_tools 噪音不映射为 skill_fetching（无 reset_tools 工具名出现在 skill_fetching 事件里）
    assert "reset_tools" not in stages
    assert result.answer_blocks[0] == "回复正文"


# ---------------------------------------------------------------------------
# SI-6：推理块透传（show_thinking=True）/ 剥离（False）
# ---------------------------------------------------------------------------
async def test_si6_thinking_passthrough_when_show_thinking() -> None:
    """SI-6a：show_thinking=True 时推理块透传到 stream_callback。"""
    from agentscope.message import ThinkingBlock

    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _thinking_text("这是推理", "可见正文"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    tokens, stream_cb = _capturing_stream()
    result = await run_chat_turn_async(
        "查 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
        stream_callback=stream_cb,
        show_thinking=True,
    )
    joined = "".join(tokens)
    assert "推理" in joined  # 推理被透传到流式 token
    assert "可见正文" in joined
    # show_thinking=True 时 answer_blocks 保留推理块（与旧 _strip_thinking(show_thinking=True) 一致）
    assert "推理" in result.answer_blocks[0]
    assert "可见正文" in result.answer_blocks[0]


async def test_si6_thinking_stripped_when_not_show_thinking() -> None:
    """SI-6b：show_thinking=False 时推理块被剥离，不进 stream_callback。"""
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {"question": "005827"}),
            _thinking_text("这是推理", "可见正文"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    tokens, stream_cb = _capturing_stream()
    result = await run_chat_turn_async(
        "查 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
        stream_callback=stream_cb,
        show_thinking=False,
    )
    joined = "".join(tokens)
    assert "推理" not in joined  # 推理被剥离
    assert "可见正文" in joined


# ---------------------------------------------------------------------------
# SI-7：审计两层事件 tool_call + reply_outcome + answer_id 贯穿
# ---------------------------------------------------------------------------
async def test_si7_audit_two_layer_events_and_answer_id_threading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SI-7：AuditMiddleware 产出 tool_call（per-occurrence）+ reply_outcome（per-reply，
    self_healed 场景）两层事件，answer_id 经 contextvars 贯穿所有事件。"""
    captured: list[tuple[str, dict, str]] = []

    def _fake_append(answer_id: str, event_type: str, payload: dict, **kw: Any) -> bool:
        captured.append((event_type, payload, answer_id))
        return True

    monkeypatch.setattr("audit.append_event", _fake_append)
    # self_heal 场景：先非白名单工具（ERROR 回灌）-> 自愈合法工具 -> 成功
    # -> outcome=self_healed -> 发 reply_outcome
    model = ScriptedChatModel(
        [
            _tool_call("delete_database", {"sql": "x"}),
            _tool_call("query_fund_detail", {"question": "005827"}),
            _text("完成。"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    result = await run_chat_turn_async(
        "查 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=True,
    )
    tool_calls = [p for t, p, _ in captured if t == "tool_call"]
    outcomes = [p for t, p, _ in captured if t == "reply_outcome"]
    assert tool_calls, "应有 tool_call 审计事件"
    assert outcomes, "self_healed 场景应有 reply_outcome 事件"
    assert outcomes[0]["outcome"] == "self_healed"
    # answer_id 贯穿：所有事件携带 result.answer_id
    assert all(aid == result.answer_id for _, _, aid in captured if aid)


# ---------------------------------------------------------------------------
# SI-8 / SI-9：栅栏 #1（臆测代码被拒 / raw code 可信集校验）
# ---------------------------------------------------------------------------
async def test_si8_hallucinated_code_rejected_by_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SI-8：resolve_fund_code 对臆测代码 raise AgentOrientedException（栅栏 #1），
    回灌自愈 -> 模型改用合法工具/名称。"""
    from agentscope.exception import AgentOrientedException

    async def _resolve_reject(query: str) -> str:
        raise AgentOrientedException("代码 999999 不在可信集内")

    async def _detail_impl(question: str) -> str:
        return json.dumps({"payload": {"ok": True, "funds": [{"symbol": "005827"}]}}, ensure_ascii=False)

    toolkit = _stub_toolkit(
        [(_detail_impl, "query_fund_detail"), (_resolve_reject, "resolve_fund_code")]
    )
    model = ScriptedChatModel(
        [
            _tool_call("resolve_fund_code", {"query": "999999"}),  # 臆测代码 -> 拒
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("完成。"),
        ]
    )
    result = await run_chat_turn_async(
        "查 999999 的详情",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    # 自愈后正常完成（未崩溃、产出回复）
    assert "完成" in (result.answer_blocks[0] if result.answer_blocks else "")


async def test_si9_raw_code_trusted_set_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SI-9：resolve_fund_code 经 fund_code_registry.is_trusted 校验 raw code（栅栏 #1 基座）。
    注入假 registry：005827 可信、999999 不可信。"""
    import agents.skills.fund_code_registry as reg

    fake_trusted = {"005827"}

    monkeypatch.setattr(reg, "is_trusted", lambda c: c in fake_trusted)
    monkeypatch.setattr(
        reg,
        "resolve",
        lambda c: type("R", (), {"matched": True, "hits": [type("H", (), {"code": c, "name": "n"})()]})()
        if c in fake_trusted
        else type("R", (), {"matched": False, "hits": []})(),
    )
    # 用真实 resolve_fund_code（经假 registry）：臆测代码被拒 -> 自愈
    from agents.tools.fund_tools import resolve_fund_code

    async def _detail_impl(question: str) -> str:
        return json.dumps({"payload": {"ok": True, "funds": [{"symbol": "005827"}]}}, ensure_ascii=False)

    toolkit = Toolkit(
        tools=[
            FunctionTool(_detail_impl, name="query_fund_detail", is_read_only=True),
            FunctionTool(resolve_fund_code, name="resolve_fund_code", is_read_only=True),
        ]
    )
    model = ScriptedChatModel(
        [
            _tool_call("resolve_fund_code", {"query": "999999"}),  # 臆测 -> is_trusted=False -> 拒
            _tool_call("resolve_fund_code", {"query": "005827"}),  # 可信 -> 放行
            _text("完成。"),
        ]
    )
    result = await run_chat_turn_async(
        "查 999999 和 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    assert "完成" in (result.answer_blocks[0] if result.answer_blocks else "")


# ---------------------------------------------------------------------------
# SI-10：栅栏 #3 case B（max_iters 耗尽 -> 启发式兜底 + degraded_fallback）
# ---------------------------------------------------------------------------
async def test_si10_max_iters_exhausted_triggers_heuristic_fallback() -> None:
    """SI-10：模型持续发非白名单 tool_call -> max_iters 耗尽 -> 启发式兜底降级路径，
    degraded_fallback 标记 + structured_outputs 不放宽（仍 single/compare 形状）。"""
    model = ScriptedChatModel([_tool_call("delete_database", {"sql": "x"})])
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    fb = _stub_fallback()
    result = await run_chat_turn_async(
        "查一下 005827",
        model=model,
        toolkit=toolkit,
        fallback=fb,
        use_compliance=False,
        use_audit=False,
    )
    # degraded_fallback 标记
    assert result.trace.get("degraded_fallback") is True
    assert result.trace.get("fallback_reason") == "max_iters_exceeded"
    # structured_outputs 不放宽：兜底产出 single 形状（或 abort 时 None，但不放宽为错形状）
    if result.structured_outputs:
        assert result.structured_outputs[0]["mode"] in ("single", "compare")


# ---------------------------------------------------------------------------
# SI-11：栅栏 #2 M4 无效 tool_call 重试自愈 / M3 ALLOW 放行
# ---------------------------------------------------------------------------
async def test_si11_m4_invalid_tool_call_self_heal_and_m3_allow() -> None:
    """SI-11：缺参 tool_call -> M1/M4 ERROR 回灌 -> 模型自愈；4 只读工具 ALLOW 放行（M3）。"""
    ctx = build_fund_permission_context()
    assert set(ctx.allow_rules.keys()) == {
        "query_fund_rank", "query_fund_detail", "resolve_fund_code", "query_knowledge_base"
    }
    model = ScriptedChatModel(
        [
            _tool_call("query_fund_detail", {}),  # 缺 question -> 校验拒 -> 回灌
            _tool_call("query_fund_detail", {"question": "005827"}),  # 自愈
            _text("自愈完成。"),
        ]
    )
    toolkit = _stub_toolkit([(_detail_single_impl, "query_fund_detail")])
    result = await run_chat_turn_async(
        "查 005827",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    assert "自愈完成" in (result.answer_blocks[0] if result.answer_blocks else "")
    assert model.call_count >= 2  # 错误回灌后重试


# ---------------------------------------------------------------------------
# SI-12：栅栏 #2 M5 部分工具失败反馈 + 栅栏 #3 case A（LLM-down -> 兜底，structured 不放宽）
# ---------------------------------------------------------------------------
async def test_si12_m5_partial_failure_feedback() -> None:
    """SI-12a：一轮多工具，query_fund_detail 成功、query_knowledge_base 失败 ->
    合法结果保留、失败独立反馈（M5）。"""
    async def _fail_impl(question: str, top_k: int = 10) -> str:
        raise RuntimeError("stub boom")

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
            _text("已分析（部分失败已隔离）。"),
        ]
    )
    result = await run_chat_turn_async(
        "查 005827 并问定投",
        model=model,
        toolkit=toolkit,
        use_compliance=False,
        use_audit=False,
    )
    # agent 未崩溃、产出回复
    assert "已分析" in (result.answer_blocks[0] if result.answer_blocks else "")


async def test_si12b_llm_down_triggers_fallback_structured_not_relaxed() -> None:
    """SI-12b：栅栏 #3 case A（LLM-down）-> 启发式兜底 + degraded_fallback + structured 不放宽。"""
    from model_gateway.exceptions import ModelGatewayError

    model = RaisingChatModel(ModelGatewayError("LLM 熔断"))
    toolkit = _full_stub_toolkit()
    fb = _stub_fallback()
    result = await run_chat_turn_async(
        "查一下 005827 的详情",
        model=model,
        toolkit=toolkit,
        fallback=fb,
        use_compliance=False,
        use_audit=False,
    )
    assert result.trace.get("degraded_fallback") is True
    assert result.trace.get("fallback_reason") == "model_unavailable"
    if result.structured_outputs:
        assert result.structured_outputs[0]["mode"] in ("single", "compare")


# ---------------------------------------------------------------------------
# 兜底：空输入快速返回
# ---------------------------------------------------------------------------
async def test_empty_input_returns_empty() -> None:
    result = await run_chat_turn_async("", use_compliance=False, use_audit=False)
    assert result.answer_blocks == [""]
    assert result.compliance.get("reason") == "空输入"
