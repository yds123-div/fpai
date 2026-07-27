# -*- coding: utf-8 -*-
"""T9 (#27)：启发式兜底共存（栅栏 #3）端到端验证。

测试 seam（spec #18 / issue #27）：脚本化假 ``ChatModelBase`` + 桩取数工具 +
桩 resolve/kb（不打真实 LLM/akshare/Milvus），对照 #27 验收五项：

1. 假模型抛异常（LLM-down）-> 启发式兜底独立降级路径触发
   （``drive_with_fallback`` catch A 异常 -> ``reason="model_unavailable"``）。
2. ``degraded_fallback`` 标记正确（``FallbackResult.degraded_fallback`` + progress 阶段
   + reason 标 A/B）。
3. structured_outputs 在降级下不被放宽（仍按 single/compare 形状产出；kb/abort -> None）。
4. 栅栏 #1 在降级下不放宽（臆测基金代码经 ``resolve_fund_code`` 校验被拒 -> abort，
   不臆造、structured_output=None）。
5. 兜底路径与 ShapeAdapter 续流共存（不改 ShapeAdapter；复用 progress/stream 通路；
   case A 干净从零 / case B 续流接 prior_text；model_first_token 只在 case A 发）。

辅助：``_ScriptedAgent``（事件序列）+ ``_RaisingModel`` / 非白名单循环模型（触发 A/B）。

运行：cd backend && uv run pytest ../tests/test_heuristic_fallback.py -c pyproject.toml -v
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from agentscope.credential import OpenAICredential
from agentscope.exception import AgentOrientedException
from agentscope.message import TextBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason, OpenAIChatModel
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

from agents.native_agent.assembly import build_fund_agent
from agents.native_agent.heuristic_fallback import (
    HeuristicFallback,
    drive_with_fallback,
    heuristic_classify,
)
from agents.native_agent.shape_adapter import ShapeAdapter
from agents.tools.fund_tools import build_fund_permission_context


# ---------------------------------------------------------------------------
# 桩取数工具（async -> JSON 字符串，与 FunctionTool impl 同形态）
# ---------------------------------------------------------------------------
async def _rank_impl(question: str) -> str:
    return json.dumps(
        {"ok": True, "funds": [{"symbol": "005827"}, {"symbol": "161725"}]},
        ensure_ascii=False,
    )


async def _detail_single_impl(question: str) -> str:
    return json.dumps(
        {"payload": {"ok": True, "funds": [{"symbol": "005827", "name": "基金A"}]}},
        ensure_ascii=False,
    )


async def _detail_multi_impl(question: str) -> str:
    return json.dumps(
        {
            "payload": {
                "ok": True,
                "funds": [
                    {"symbol": "005827", "name": "基金A"},
                    {"symbol": "161725", "name": "基金B"},
                ],
            }
        },
        ensure_ascii=False,
    )


async def _kb_impl(question: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "count": 1,
            "chunks": [{"source": "faq", "chunk_text": "基金定投需开户。"}],
        },
        ensure_ascii=False,
    )


def _resolve_ok(query: str):
    """可信代码放行：返回 code_provided 记录（含 code）。"""

    async def _impl(query: str) -> str:
        return json.dumps(
            {
                "ok": True,
                "mode": "code_provided",
                "codes": [{"code": "005827", "name": "基金A", "type": "混合", "score": 120.0}],
            },
            ensure_ascii=False,
        )

    return _impl


def _resolve_multi_ok(query: str):
    """多只可信代码放行。"""

    async def _impl(query: str) -> str:
        return json.dumps(
            {
                "ok": True,
                "mode": "code_provided",
                "codes": [
                    {"code": "005827", "name": "基金A", "type": "混合", "score": 120.0},
                    {"code": "161725", "name": "基金B", "type": "指数", "score": 120.0},
                ],
            },
            ensure_ascii=False,
        )

    return _impl


def _resolve_reject(query: str):
    """臆测代码 / 查不到名称 -> raise AgentOrientedException（栅栏 #1 拒绝信号）。"""

    async def _impl(query: str) -> str:
        raise AgentOrientedException(
            f"基金代码 {query} 不在可信集内，可能是臆测代码。",
        )

    return _impl


def _resolve_name_hit(query: str):
    """名称命中 -> 返回 matches（含 code），供名称分支取 code。"""

    async def _impl(query: str) -> str:
        return json.dumps(
            {
                "ok": True,
                "mode": "name_to_code",
                "matches": [{"code": "005827", "name": "基金A", "type": "混合", "score": 120.0}],
            },
            ensure_ascii=False,
        )

    return _impl


# ---------------------------------------------------------------------------
# 假模型：非白名单循环（触发 B max_iters）/ 抛异常（触发 A model_unavailable）
# ---------------------------------------------------------------------------
class _ScriptedModel(ChatModelBase):
    """按 ``responses`` 顺序返回的假模型（max_retries=0 防内层重试叠加）。"""

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

    async def _call_api(self, model_name, messages, tools=None, tool_choice=None, **kw):
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return self._responses[idx]


class _RaisingModel(ChatModelBase):
    """_call_api 恒抛异常 -> 模型 API 失败（LLM-down，case A）。"""

    def __init__(self, exc: Exception) -> None:
        super().__init__(
            credential=OpenAICredential(api_key="stub", base_url="stub"),
            model="stub-model",
            parameters=OpenAIChatModel.Parameters(),
            stream=True,
            max_retries=0,
        )
        self._exc = exc
        self.call_count = 0

    async def _call_api(self, model_name, messages, tools=None, tool_choice=None, **kw):
        self.call_count += 1
        raise self._exc


def _tool_call_resp(name: str, args: dict) -> ChatResponse:
    from agentscope.message import ToolCallBlock

    return ChatResponse(
        content=[ToolCallBlock(id="c1", name=name, input=json.dumps(args, ensure_ascii=False))],
        is_last=True,
        finished_reason=FinishedReason.COMPLETED,
    )


def _stub_toolkit() -> Toolkit:
    return Toolkit(tools=[FunctionTool(_detail_single_impl, name="query_fund_detail", is_read_only=True)])


def _state() -> AgentState:
    return AgentState(permission_context=build_fund_permission_context())


def _ask(msg: str) -> UserMsg:
    return UserMsg(name="user", content=[TextBlock(text=msg)])


def _make_fallback(
    *,
    rank=None, detail=None, resolve=None, kb=None, progress=None, stream=None, show_thinking=False
) -> HeuristicFallback:
    return HeuristicFallback(
        progress_callback=progress,
        stream_callback=stream,
        show_thinking=show_thinking,
        rank_tool=rank or _rank_impl,
        detail_tool=detail or _detail_single_impl,
        resolve_tool=resolve or _resolve_ok(""),
        kb_tool=kb or _kb_impl,
    )


# ===========================================================================
# 验收 0：heuristic_classify 改造搬迁行为零变更
# ===========================================================================
def test_heuristic_classify_relocated_behavior_zero_change() -> None:
    """heuristic_classify 行为不变（四分类 + 边沿）--T10 删除 fund_agent_framework 后
    此函数已是单一权威源（存活栅栏 #3），不再有 legacy 别名需校验。"""
    assert heuristic_classify("对比 005827 和 161725") == "product_compare"
    assert heuristic_classify("近一月涨幅前5的基金") == "product_query"
    assert heuristic_classify("005827 怎么样") == "product_interpret"
    # 含"基金"关键词但无其它命中 -> product_query（旧逻辑，不放宽为 other）
    assert heuristic_classify("基金定投怎么开户") == "product_query"
    # 无业务关键词 -> other
    assert heuristic_classify("定投怎么开户") == "other"
    assert heuristic_classify("") == "other"


# ===========================================================================
# 验收 1 + 2：LLM-down -> 兜底触发；degraded_fallback 标记正确
# ===========================================================================
async def test_llm_down_model_raises_triggers_fallback() -> None:
    """case A：假模型 _call_api 抛异常 -> drive_with_fallback catch -> 兜底触发。"""
    progress: list[str] = []
    tokens: list[str] = []

    async def prog(stage: str, **kw: Any) -> None:
        progress.append(stage)

    def stream(t: str) -> None:
        tokens.append(t)

    agent, _ = build_fund_agent(
        model=_RaisingModel(RuntimeError("LLM down")),
        toolkit=_stub_toolkit(),
        state=_state(),
        attach_audit=False,
        max_iters=2,
    )
    fallback = _make_fallback(progress=prog, stream=stream, resolve=_resolve_ok(""))
    # adapter 与 fallback 共用同一套 SSE 回调（栅栏 #6 续流共存）
    adapter = ShapeAdapter(progress_callback=prog, stream_callback=stream)
    final_text, result = await drive_with_fallback(adapter, agent, _ask("005827 怎么样"), fallback)
    # 兜底触发：result 非 None、标记正确
    assert result is not None
    assert result.degraded_fallback is True
    assert result.reason == "model_unavailable"
    assert result.category == "product_interpret"
    # 流式契约共存：ShapeAdapter 先发 llm_generating（模型开始），兜底再发 degraded_fallback
    assert "llm_generating" in progress
    assert "degraded_fallback" in progress
    assert "model_first_token" in progress  # case A 干净从零 -> 兜底发 TTFT
    # token 经 stream_callback 流出
    assert "".join(tokens) == final_text
    assert final_text  # 非空


async def test_max_iters_exceeded_triggers_fallback() -> None:
    """case B：模型持续非白名单 tool_call -> max_iters 耗尽 -> 兜底触发。"""
    progress: list[str] = []
    tokens: list[str] = []

    async def prog(stage: str, **kw: Any) -> None:
        progress.append(stage)

    def stream(t: str) -> None:
        tokens.append(t)

    # 恒发非白名单 tool_call -> ExceedMaxItersEvent
    agent, _ = build_fund_agent(
        model=_ScriptedModel([_tool_call_resp("delete_database", {"sql": "x"})]),
        toolkit=_stub_toolkit(),
        state=_state(),
        attach_audit=False,
        max_iters=2,
    )
    fallback = _make_fallback(progress=prog, stream=stream, resolve=_resolve_ok(""))
    # adapter 与 fallback 共用同一套 SSE 回调（栅栏 #6 续流共存）
    adapter = ShapeAdapter(progress_callback=prog, stream_callback=stream)
    final_text, result = await drive_with_fallback(adapter, agent, _ask("005827 怎么样"), fallback)
    assert result is not None
    assert result.degraded_fallback is True
    assert result.reason == "max_iters_exceeded"
    # ShapeAdapter 先发了 exceed_max_iters，兜底再发 degraded_fallback
    assert "exceed_max_iters" in progress
    assert "degraded_fallback" in progress


# ===========================================================================
# 验收 3：structured_outputs 在降级下不被放宽（仍按 single/compare 形状产出）
# ===========================================================================
async def test_structured_single_for_one_fund_under_degradation() -> None:
    """单只详情 -> structured_output mode=single（不放宽为空/None）。"""
    fb = _make_fallback(detail=_detail_single_impl, resolve=_resolve_ok(""))
    r = await fb.run("model_unavailable", "005827 怎么样")
    assert r.structured_output is not None
    assert r.structured_output["mode"] == "single"


async def test_structured_compare_for_two_funds_under_degradation() -> None:
    """多只详情 -> structured_output mode=compare（不放宽为 single）。"""
    fb = _make_fallback(detail=_detail_multi_impl, resolve=_resolve_multi_ok(""))
    r = await fb.run("max_iters_exceeded", "对比 005827 和 161725")
    assert r.structured_output is not None
    assert r.structured_output["mode"] == "compare"


async def test_structured_single_for_rank_under_degradation() -> None:
    """榜单（即使多只）-> single（榜单不是对比，不放宽为 compare）。"""
    fb = _make_fallback(rank=_rank_impl, resolve=_resolve_ok(""))
    r = await fb.run("model_unavailable", "近一月涨幅前5的基金")
    assert r.structured_output is not None
    assert r.structured_output["mode"] == "single"
    assert r.category == "product_query"


async def test_structured_none_for_kb_under_degradation() -> None:
    """other/kb 无 builder -> structured_output=None（不臆造结构）。"""
    fb = _make_fallback(kb=_kb_impl, resolve=_resolve_ok(""))
    r = await fb.run("model_unavailable", "定投怎么开户")
    assert r.structured_output is None
    assert r.category == "other"
    assert r.aborted is False


# ===========================================================================
# 验收 4：栅栏 #1 在降级下不放宽（臆测基金代码仍被拒）
# ===========================================================================
async def test_fabricated_code_rejected_aborts_without_relaxing() -> None:
    """臆测代码 999999 -> resolve 拒（raise）-> abort；不臆造、structured=None、detail 不被调。"""
    detail_calls: list[str] = []

    async def detail_spy(question: str) -> str:
        detail_calls.append(question)
        return await _detail_single_impl(question)

    fb = _make_fallback(detail=detail_spy, resolve=_resolve_reject(""))
    r = await fb.run("model_unavailable", "分析 999999 这只基金")
    assert r.aborted is True
    # 不放宽：structured_output 为 None（不产出臆测代码的结构）
    assert r.structured_output is None
    # detail 工具未被调（臆测代码未泄漏进取数）
    assert detail_calls == []
    # abort 文案对用户可见
    assert "基金代码" in r.abort_message
    assert r.final_text  # 仍有降级提示回复（非空响应）


async def test_unresolvable_name_aborts() -> None:
    """用户给名称但查不到代码 -> resolve 拒 -> abort（不臆造代码）。"""
    fb = _make_fallback(detail=_detail_single_impl, resolve=_resolve_reject(""))
    r = await fb.run("max_iters_exceeded", "分析某不存在的基金A怎么样")
    assert r.aborted is True
    assert r.structured_output is None


async def test_trusted_code_passes_fence_one() -> None:
    """可信代码 005827 -> resolve 放行 -> detail 取数 -> structured 产出（正路）。"""
    detail_calls: list[str] = []

    async def detail_spy(question: str) -> str:
        detail_calls.append(question)
        return await _detail_single_impl(question)

    fb = _make_fallback(detail=detail_spy, resolve=_resolve_ok(""))
    r = await fb.run("model_unavailable", "005827 怎么样")
    assert r.aborted is False
    assert r.structured_output is not None
    assert r.structured_output["mode"] == "single"
    # 可信代码经 resolve 校验后喂给 detail
    assert detail_calls and "005827" in detail_calls[0]


async def test_name_resolved_then_detail_fetched() -> None:
    """用户给名称（无代码）-> resolve 名称命中 -> 取 code -> detail 取数（栅栏 #1 正路）。"""
    detail_calls: list[str] = []

    async def detail_spy(question: str) -> str:
        detail_calls.append(question)
        return await _detail_single_impl(question)

    fb = _make_fallback(detail=detail_spy, resolve=_resolve_name_hit(""))
    r = await fb.run("model_unavailable", "基金A 怎么样")
    assert r.aborted is False
    assert r.structured_output is not None
    # resolve 出的 code 喂给了 detail
    assert detail_calls and "005827" in detail_calls[0]


# ===========================================================================
# 验收 5：兜底路径与 ShapeAdapter 续流共存（不破坏流式契约）
# ===========================================================================
async def test_fallback_uses_shared_callbacks_emits_degraded_stage() -> None:
    """兜底复用 progress/stream 通路：发 degraded_fallback 阶段 + token 经 stream_callback。"""
    progress: list[tuple[str, dict]] = []
    tokens: list[str] = []

    async def prog(stage: str, **kw: Any) -> None:
        progress.append((stage, kw))

    def stream(t: str) -> None:
        tokens.append(t)

    fb = _make_fallback(progress=prog, stream=stream, detail=_detail_single_impl, resolve=_resolve_ok(""))
    r = await fb.run("model_unavailable", "005827 怎么样")
    # degraded_fallback 阶段带 reason + category
    degraded = [p for p in progress if p[0] == "degraded_fallback"]
    assert len(degraded) == 1
    assert degraded[0][1]["reason"] == "model_unavailable"
    assert degraded[0][1]["category"] == "product_interpret"
    # token 经 stream 流出且拼回 = final_text
    assert "".join(tokens) == r.final_text


async def test_model_first_token_only_for_case_a() -> None:
    """case A（prior_text 空）发 model_first_token；case B（prior_text 非空）不发。"""
    # case A
    prog_a: list[str] = []

    async def prog_a_cb(stage: str, **kw: Any) -> None:
        prog_a.append(stage)

    fb_a = _make_fallback(progress=prog_a_cb, detail=_detail_single_impl, resolve=_resolve_ok(""))
    await fb_a.run("model_unavailable", "005827 怎么样")
    assert "model_first_token" in prog_a

    # case B：prior_text 非空 -> TTFT 已由 ShapeAdapter 发过，兜底不再发
    prog_b: list[str] = []

    async def prog_b_cb(stage: str, **kw: Any) -> None:
        prog_b.append(stage)

    fb_b = _make_fallback(progress=prog_b_cb, detail=_detail_single_impl, resolve=_resolve_ok(""))
    r_b = await fb_b.run("max_iters_exceeded", "005827 怎么样", prior_text="已流部分")
    assert "model_first_token" not in prog_b
    # 续流：final_text = prior_text + 分隔 + 降级内容
    assert r_b.final_text.startswith("已流部分")
    assert "已流部分" in r_b.final_text


async def test_drive_with_fallback_normal_completion_no_fallback() -> None:
    """agent 正常完成（无异常、无 exceed）-> 不触发兜底（result=None）。"""
    from agentscope.message import TextBlock

    # 模型：先调合法工具，再给最终文本 -> 正常完成
    model = _ScriptedModel(
        [
            _tool_call_resp("query_fund_detail", {"question": "005827"}),
            ChatResponse(
                content=[TextBlock(text="正常回复。")],
                is_last=True,
                finished_reason=FinishedReason.COMPLETED,
            ),
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False, max_iters=4
    )
    fallback = _make_fallback(resolve=_resolve_ok(""))
    adapter = ShapeAdapter()
    final_text, result = await drive_with_fallback(adapter, agent, _ask("查 005827"), fallback)
    assert result is None  # 未触发兜底
    assert "正常回复" in final_text


# ---------------------------------------------------------------------------
# 回调鲁棒性
# ---------------------------------------------------------------------------
async def test_callback_exception_does_not_break_fallback() -> None:
    """回调抛异常被吞掉（best-effort），不阻断降级路径。"""
    def bad_prog(stage: str, **kw: Any) -> None:
        raise RuntimeError("callback boom")

    def bad_stream(t: str) -> None:
        raise RuntimeError("callback boom")

    fb = HeuristicFallback(
        progress_callback=bad_prog,
        stream_callback=bad_stream,
        detail_tool=_detail_single_impl,
        resolve_tool=_resolve_ok(""),
        rank_tool=_rank_impl,
        kb_tool=_kb_impl,
    )
    r = await fb.run("model_unavailable", "005827 怎么样")
    # 不抛异常、降级完成
    assert r.degraded_fallback is True
    assert r.structured_output is not None


async def test_none_callbacks_safe() -> None:
    """progress/stream 回调缺省 None 时不报错。"""
    fb = HeuristicFallback(
        detail_tool=_detail_single_impl,
        resolve_tool=_resolve_ok(""),
        rank_tool=_rank_impl,
        kb_tool=_kb_impl,
    )
    r = await fb.run("model_unavailable", "005827 怎么样")
    assert r.degraded_fallback is True
