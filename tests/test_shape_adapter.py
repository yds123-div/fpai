# -*- coding: utf-8 -*-
"""T8 (#26)：ShapeAdapter 流式保形（栅栏 #6）端到端验证。

测试 seam（spec #18 / issue #26）：脚本化假 streaming ``ChatModelBase`` 产出事件
序列，断言阶段序列 + token 分片。对照 #26 验收五项：

1. ``ShapeAdapter`` 把 ``reply_stream`` 事件映射到 ``progress_callback`` /
   ``stream_callback``，5 核心阶段全命中
   （accepted / thinking / skill_fetching / llm_generating / model_first_token / done）。
2. token 分片正确（首个 token 先发 ``model_first_token`` 进度）。
3. ``ihad`` 透传（show_thinking=True）/ 剥离（show_thinking=False）--
   含原生分离（ThinkingBlock 事件）与 provider 内联（text 里夹 ``ihad``）两条路径。
4. ``reset_tools`` 噪音在 SSE 层被过滤（前端不收到脏事件）。
5. OpenAI 兼容端点与 DashScope 双 provider 保形（分离/内联两条路径产出同形）。

辅助 ``_ScriptedAgent`` 直接喂事件序列，验证 ``RequireUserConfirmEvent`` /
``ExceedMaxItersEvent`` 等难经真实 agent 触发的边沿映射（HITL 暂停 / 耗尽）。

运行：cd backend && uv run pytest ../tests/test_shape_adapter.py -c pyproject.toml -v
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Callable

import pytest
from agentscope.credential import OpenAICredential
from agentscope.event import (
    ExceedMaxItersEvent,
    ModelCallStartEvent,
    ReplyEndEvent,
    ReplyStartEvent,
    RequireUserConfirmEvent,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ThinkingBlockEndEvent,
    ThinkingBlockStartEvent,
    ToolCallStartEvent,
    ToolResultStartEvent,
)
from agentscope.message import TextBlock, ThinkingBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason, OpenAIChatModel
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

from agents.native_agent.assembly import build_fund_agent
from agents.native_agent.shape_adapter import (
    CORE_STAGES,
    NOISE_TOOL_NAMES,
    ShapeAdapter,
    _ThinkFilter,
)
from agents.tools.fund_tools import build_fund_permission_context

#: 推理块开/闭标签（与 ``orchestrator/run.py`` 一致；此处显式字面量避免渲染歧义）。
_THINK_OPEN = chr(0x3c) + "think" + chr(0x3e)        # <think>
_THINK_CLOSE = chr(0x3c) + "/think" + chr(0x3e)     # </think>


# ---------------------------------------------------------------------------
# 假 streaming ChatModelBase：按脚本顺序返回响应（tool_call 或 token 流）
# ---------------------------------------------------------------------------
class StreamingScriptedModel(ChatModelBase):
    """按 ``step_factories`` 顺序返回的假流式模型。

    每个 step_factory 是 ``() -> ChatResponse | AsyncGenerator[ChatResponse]``：
    - 返回 ``ChatResponse``（is_last=True）-> 非流式（如 tool_call）
    - 返回 async generator -> token 级流式（yield 多个 is_last=False 分片，
      base ``__call__`` 自动累积出末尾 is_last=True 的完整响应）。
    """

    def __init__(
        self, step_factories: list[Callable[[], Any]]
    ) -> None:
        super().__init__(
            credential=OpenAICredential(api_key="stub", base_url="stub"),
            model="stub-model",
            parameters=OpenAIChatModel.Parameters(),
            stream=True,
            max_retries=0,
        )
        self._steps = list(step_factories)
        self.call_count = 0

    async def _call_api(
        self,
        model_name: str,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> Any:
        idx = min(self.call_count, len(self._steps) - 1)
        self.call_count += 1
        return self._steps[idx]()


def _tool_call_step(name: str, args: dict, call_id: str = "c1") -> Callable[[], ChatResponse]:
    def _factory() -> ChatResponse:
        return ChatResponse(
            content=[
                ToolCallBlock(
                    id=call_id, name=name, input=json.dumps(args, ensure_ascii=False)
                )
            ],
            is_last=True,
            finished_reason=FinishedReason.COMPLETED,
        )

    return _factory


def _reset_tools_step(call_id: str = "r1") -> Callable[[], ChatResponse]:
    """构造 reset_tools meta 工具调用（input={}, agent 会真执行并发出噪音事件）。"""
    return _tool_call_step("reset_tools", {}, call_id=call_id)


def _text_stream_step(tokens: list[str]) -> Callable[[], AsyncGenerator[ChatResponse, None]]:
    def _factory() -> AsyncGenerator[ChatResponse, None]:
        async def _gen() -> AsyncGenerator[ChatResponse, None]:
            for t in tokens:
                yield ChatResponse(content=[TextBlock(text=t)], is_last=False)

        return _gen()

    return _factory


def _thinking_then_text_stream_step(
    thinking_tokens: list[str], text_tokens: list[str]
) -> Callable[[], AsyncGenerator[ChatResponse, None]]:
    """分离推理流（OpenAI 兼容 / DashScope 原生形态）：先 ThinkingBlock 分片，再 TextBlock 分片。"""

    def _factory() -> AsyncGenerator[ChatResponse, None]:
        async def _gen() -> AsyncGenerator[ChatResponse, None]:
            for t in thinking_tokens:
                yield ChatResponse(
                    content=[ThinkingBlock(thinking=t)], is_last=False
                )
            for t in text_tokens:
                yield ChatResponse(content=[TextBlock(text=t)], is_last=False)

        return _gen()

    return _factory


def _inlined_thinking_text_stream_step(
    parts: list[str],
) -> Callable[[], AsyncGenerator[ChatResponse, None]]:
    """内联推理流（provider 未分离：``ihad...andbox`` 夹在 text content 里）。"""

    def _factory() -> AsyncGenerator[ChatResponse, None]:
        async def _gen() -> AsyncGenerator[ChatResponse, None]:
            for p in parts:
                yield ChatResponse(content=[TextBlock(text=p)], is_last=False)

        return _gen()

    return _factory


# ---------------------------------------------------------------------------
# 桩取数工具 + toolkit/permission（复用 T6/T7 seam 形态）
# ---------------------------------------------------------------------------
async def _detail_single_impl(question: str) -> str:
    return json.dumps(
        {"payload": {"ok": True, "funds": [{"symbol": "005827"}]}}, ensure_ascii=False
    )


def _stub_toolkit() -> Toolkit:
    return Toolkit(
        tools=[FunctionTool(_detail_single_impl, name="query_fund_detail", is_read_only=True)]
    )


def _state() -> AgentState:
    return AgentState(permission_context=build_fund_permission_context())


def _ask(msg: str) -> UserMsg:
    return UserMsg(name="user", content=[TextBlock(text=msg)])


# ---------------------------------------------------------------------------
# 纯事件序列假 agent（测难经真实 agent 触发的边沿映射：HITL / 耗尽 / 确定性核心映射）
# ---------------------------------------------------------------------------
class _ScriptedAgent:
    """最小假 agent：``reply_stream`` 按脚本 yield 事件序列。"""

    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)

    async def reply_stream(self, msg: Any) -> AsyncGenerator[Any, None]:  # noqa: ARG002
        for ev in self._events:
            yield ev


def _core_event_sequence(tool_name: str = "query_fund_detail") -> list[Any]:
    """一条命中 5 核心阶段的事件序列（accepted 由 adapter 自发，不在此）。"""
    return [
        ReplyStartEvent(session_id="s", reply_id="r", name="fund_agent"),
        ModelCallStartEvent(reply_id="r", model_name="stub"),
        ToolCallStartEvent(reply_id="r", tool_call_id="c1", tool_call_name=tool_name),
        ToolResultStartEvent(reply_id="r", tool_call_id="c1", tool_call_name=tool_name),
        ModelCallStartEvent(reply_id="r", model_name="stub"),
        TextBlockDeltaEvent(reply_id="r", block_id="b1", delta="你好"),
        TextBlockDeltaEvent(reply_id="r", block_id="b1", delta="世界"),
        ReplyEndEvent(session_id="s", reply_id="r"),
    ]


# ---------------------------------------------------------------------------
# 辅助：跑 adapter + 收集 progress/token
# ---------------------------------------------------------------------------
async def _drive_collect(
    adapter: ShapeAdapter, agent: Any, msg: UserMsg
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """驱动 adapter，返回 (yielded (kind,detail), progress_stages, stream_tokens)。"""
    progress: list[str] = []
    tokens: list[str] = []

    async def prog(stage: str, **kw: Any) -> None:
        progress.append(stage)

    def stream(t: str) -> None:
        tokens.append(t)

    adapter.progress_callback = prog
    adapter.stream_callback = stream
    yielded: list[tuple[str, str]] = []
    async for kind, detail in adapter.drive(agent, msg):
        yielded.append((kind, detail))
    return yielded, progress, tokens


# ===========================================================================
# 验收 1：5 核心阶段全命中 + 事件 -> 契约映射
# ===========================================================================
async def test_five_core_stages_all_hit_via_real_agent() -> None:
    """真实 agent + 假流式模型：5 核心阶段全命中（accepted/thinking/skill_fetching/
    llm_generating/model_first_token/done）。"""
    model = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _text_stream_step(["你好", "世界", "。"]),
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter()
    _, progress, tokens = await _drive_collect(adapter, agent, _ask("查 005827"))
    # 5 核心阶段全命中
    hit = set(progress) & CORE_STAGES
    missing = CORE_STAGES - hit
    assert not missing, f"缺失核心阶段: {missing}；实际 progress={progress}"
    # accepted 在最前、done 在最后
    assert progress[0] == "accepted"
    assert progress[-1] == "done"


async def test_core_mapping_deterministic_via_scripted_agent() -> None:
    """纯事件序列假 agent：确定性验证事件 -> 阶段映射表（E3 映射逐条）。"""
    adapter = ShapeAdapter()
    yielded, progress, tokens = await _drive_collect(
        adapter, _ScriptedAgent(_core_event_sequence()), _ask("x")
    )
    # 映射表逐条：thinking / skill_fetching / llm_generating / model_first_token / done
    assert "thinking" in progress
    assert "skill_fetching" in progress
    assert "llm_generating" in progress
    assert "model_first_token" in progress
    assert "done" in progress
    # accepted 先发
    assert yielded[0] == ("progress", "accepted")
    # token 分片
    assert tokens == ["你好", "世界"]


# ===========================================================================
# 验收 2：token 分片 + 首个 token 先发 model_first_token 进度
# ===========================================================================
async def test_first_token_emits_model_first_token_before_stream() -> None:
    """首个 token 先发 model_first_token 进度，再发 token；后续 token 不重复发。"""
    adapter = ShapeAdapter()
    yielded, progress, tokens = await _drive_collect(
        adapter, _ScriptedAgent(_core_event_sequence()), _ask("x")
    )
    # model_first_token 恰好一次
    assert progress.count("model_first_token") == 1
    mft_idx = yielded.index(("progress", "model_first_token"))
    # model_first_token 紧接其后的 yielded 是首个 token
    assert yielded[mft_idx + 1] == ("token", "你好")
    # 第二个 token 前不再有 model_first_token
    second_token_idx = yielded.index(("token", "世界"))
    assert ("progress", "model_first_token") not in yielded[mft_idx + 1: second_token_idx]


async def test_token_sharding_multiple_stream_callbacks() -> None:
    """token 级流式：多个 token 各自触发一次 stream_callback。"""
    tokens_in = ["易方达蓝筹", "精选混合", "005827", "。"]
    model = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _text_stream_step(tokens_in),
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter()
    _, _, tokens = await _drive_collect(adapter, agent, _ask("查 005827"))
    assert tokens == tokens_in
    assert adapter.final_text == "".join(tokens_in)


# ===========================================================================
# 验收 3：ihad 透传 / 剥离（分离 + 内联两条路径）
# ===========================================================================
async def test_separated_thinking_passthrough_when_show_thinking() -> None:
    """原生分离推理（ThinkingBlock 事件）：show_thinking=True 透传 ihad...andbox。"""
    model = StreamingScriptedModel(
        [
            _thinking_then_text_stream_step(
                thinking_tokens=["先思考一下"], text_tokens=["答案是42"]
            )
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter(show_thinking=True)
    _, _, tokens = await _drive_collect(adapter, agent, _ask("x"))
    joined = "".join(tokens)
    # 透传：开标签 + 思考 + 闭标签 + 答案
    assert _THINK_OPEN in joined
    assert _THINK_CLOSE in joined
    assert "先思考一下" in joined
    assert "答案是42" in joined
    # 顺序：开 -> 思考 -> 闭 -> 答案
    assert joined.index(_THINK_OPEN) < joined.index("先思考一下")
    assert joined.index("先思考一下") < joined.index(_THINK_CLOSE)
    assert joined.index(_THINK_CLOSE) < joined.index("答案是42")


async def test_separated_thinking_stripped_when_not_show_thinking() -> None:
    """原生分离推理：show_thinking=False 丢弃整个 ThinkingBlock（只留答案文本）。"""
    model = StreamingScriptedModel(
        [
            _thinking_then_text_stream_step(
                thinking_tokens=["秘密推理"], text_tokens=["可见答案"]
            )
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter(show_thinking=False)
    _, _, tokens = await _drive_collect(adapter, agent, _ask("x"))
    joined = "".join(tokens)
    assert joined == "可见答案"
    assert "秘密推理" not in joined
    assert _THINK_OPEN not in joined


async def test_inlined_thinking_stripped_by_state_machine() -> None:
    """provider 内联推理（text 里夹 ihad...andbox）：show_thinking=False 时
    _ThinkFilter 状态机剥离思考块，仅留可见文本。"""
    # 跨 delta 切开标签，验证 carry 续接
    parts = [
        _THINK_OPEN + "这是一些",
        "思考内容" + _THINK_CLOSE,
        "最终可见文本",
    ]
    model = StreamingScriptedModel([_inlined_thinking_text_stream_step(parts)])
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter(show_thinking=False)
    _, _, tokens = await _drive_collect(adapter, agent, _ask("x"))
    joined = "".join(tokens)
    assert joined == "最终可见文本"
    assert "思考内容" not in joined
    assert _THINK_OPEN not in joined


async def test_inlined_thinking_passthrough_when_show_thinking() -> None:
    """provider 内联推理：show_thinking=True 时原样透传（含 ihad 标签）。"""
    parts = [_THINK_OPEN + "思考" + _THINK_CLOSE + "答案"]
    model = StreamingScriptedModel([_inlined_thinking_text_stream_step(parts)])
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter(show_thinking=True)
    _, _, tokens = await _drive_collect(adapter, agent, _ask("x"))
    joined = "".join(tokens)
    assert joined == _THINK_OPEN + "思考" + _THINK_CLOSE + "答案"


def test_think_filter_unit_cross_delta_carry() -> None:
    """_ThinkFilter 单元：标签跨 delta 分割时 carry 续接，正确剥离。"""
    f = _ThinkFilter()
    # <think 分到 delta1 末尾、> 在 delta2 开头
    assert f.feed("前文" + _THINK_OPEN[:3]) == "前文"
    rest = f.feed(_THINK_OPEN[3:] + "思考" + _THINK_CLOSE)
    assert rest == ""
    assert f.feed("后文") == "后文"


def test_think_filter_unit_no_think_tag_passthrough() -> None:
    """_ThinkFilter 单元：无 ihad 标签时原样透传。"""
    f = _ThinkFilter()
    assert f.feed("纯文本无推理") == "纯文本无推理"


def test_think_filter_unit_unclosed_think_carries() -> None:
    """_ThinkFilter 单元：未闭合 ihad 跨 delta 续接，闭合后剥离。"""
    f = _ThinkFilter()
    assert f.feed("可见" + _THINK_OPEN) == "可见"
    assert f.feed("思考中") == ""  # 仍在 think 内，丢弃
    assert f.feed(_THINK_CLOSE + "恢复") == "恢复"


# ===========================================================================
# 验收 4：reset_tools 噪音在 SSE 层被过滤
# ===========================================================================
async def test_reset_tools_noise_filtered_from_progress() -> None:
    """agent 调 reset_tools meta 工具：其 skill_fetching/skill_result 不发给前端，
    真实业务工具的 skill_fetching 仍命中。"""
    model = StreamingScriptedModel(
        [
            _reset_tools_step(),  # 噪音工具调用
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _text_stream_step(["完成"]),
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter()
    yielded, progress, tokens = await _drive_collect(adapter, agent, _ask("查 005827"))
    # reset_tools 不产生任何 skill_fetching / skill_result 观察事件
    skill_events = [d for k, d in yielded if d.startswith("skill_")]
    assert all("reset_tools" not in d for d in skill_events), skill_events
    # reset_tools 不产生 token
    assert all("reset_tools" not in t for t in tokens)
    # 真实业务工具的 skill_fetching 仍命中
    assert any(d == "skill_fetching:query_fund_detail" for _, d in yielded)
    # 5 核心阶段仍全命中（reset_tools 过滤不影响保形）
    assert not (CORE_STAGES - set(progress))


async def test_reset_tools_noise_filtered_via_scripted_agent() -> None:
    """纯事件序列：reset_tools 的 ToolCallStart/ToolResultStart 被过滤，
    同序列内真实工具仍映射。"""
    events = [
        ReplyStartEvent(session_id="s", reply_id="r", name="fund_agent"),
        ModelCallStartEvent(reply_id="r", model_name="stub"),
        ToolCallStartEvent(reply_id="r", tool_call_id="r1", tool_call_name="reset_tools"),
        ToolResultStartEvent(reply_id="r", tool_call_id="r1", tool_call_name="reset_tools"),
        ToolCallStartEvent(reply_id="r", tool_call_id="c1", tool_call_name="query_fund_detail"),
        ToolResultStartEvent(reply_id="r", tool_call_id="c1", tool_call_name="query_fund_detail"),
        TextBlockDeltaEvent(reply_id="r", block_id="b1", delta="ok"),
        ReplyEndEvent(session_id="s", reply_id="r"),
    ]
    adapter = ShapeAdapter()
    yielded, progress, _ = await _drive_collect(
        adapter, _ScriptedAgent(events), _ask("x")
    )
    skill_events = [d for k, d in yielded if d.startswith("skill_")]
    assert all("reset_tools" not in d for d in skill_events)
    assert any(d == "skill_fetching:query_fund_detail" for _, d in yielded)


def test_noise_tool_names_contains_reset_tools() -> None:
    """NOISE_TOOL_NAMES 白名单含 reset_tools（可扩展的噪音过滤集合）。"""
    assert "reset_tools" in NOISE_TOOL_NAMES


# ===========================================================================
# 验收 5：OpenAI 兼容端点与 DashScope 双 provider 保形
# ===========================================================================
async def test_dual_provider_same_shape_when_stripped() -> None:
    """双 provider 保形：分离推理（OpenAI 兼容）与内联推理（DashScope 兜底）
    在 show_thinking=False 下产出同形（仅可见文本 + 5 核心阶段全命中）。"""
    # provider A：分离推理（OpenAI 兼容原生形态）
    model_a = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _thinking_then_text_stream_step(["推理A"], ["可见A"]),
        ]
    )
    # provider B：内联推理（DashScope 未分离形态）
    model_b = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _inlined_thinking_text_stream_step(
                [_THINK_OPEN + "推理B" + _THINK_CLOSE + "可见B"]
            ),
        ]
    )
    results: list[tuple[list[str], list[str], str]] = []
    for model in (model_a, model_b):
        agent, _ = build_fund_agent(
            model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
        )
        adapter = ShapeAdapter(show_thinking=False)
        _, progress, tokens = await _drive_collect(adapter, agent, _ask("x"))
        results.append((progress, tokens, adapter.final_text))
    # 保形：两 provider 剥离推理后 final_text 均为可见文本
    assert results[0][2] == "可见A"
    assert results[1][2] == "可见B"
    # 保形：两 provider 5 核心阶段全命中（阶段序列形状一致）
    for progress, _, _ in results:
        assert not (CORE_STAGES - set(progress)), progress
    # 保形：两 provider 都有 token 分片
    assert len(results[0][1]) >= 1
    assert len(results[1][1]) >= 1


async def test_dual_provider_same_shape_when_show_thinking() -> None:
    """双 provider 保形：show_thinking=True 时都透传推理（含 ihad 标签）。"""
    model_a = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _thinking_then_text_stream_step(["推理"], ["答案"]),
        ]
    )
    model_b = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _inlined_thinking_text_stream_step(
                [_THINK_OPEN + "推理" + _THINK_CLOSE + "答案"]
            ),
        ]
    )
    for model in (model_a, model_b):
        agent, _ = build_fund_agent(
            model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
        )
        adapter = ShapeAdapter(show_thinking=True)
        _, _, tokens = await _drive_collect(adapter, agent, _ask("x"))
        joined = "".join(tokens)
        assert _THINK_OPEN in joined and _THINK_CLOSE in joined
        assert "推理" in joined and "答案" in joined


# ===========================================================================
# 边沿映射：RequireUserConfirmEvent / ExceedMaxItersEvent（_ScriptedAgent）
# ===========================================================================
async def test_require_user_confirm_maps_to_awaiting_confirm() -> None:
    """RequireUserConfirmEvent（HITL 暂停）-> progress('awaiting_confirm')。"""
    events = [
        ReplyStartEvent(session_id="s", reply_id="r", name="fund_agent"),
        ToolCallStartEvent(reply_id="r", tool_call_id="d1", tool_call_name="dangerous_op"),
        RequireUserConfirmEvent(
            reply_id="r",
            tool_calls=[
                ToolCallBlock(id="d1", name="dangerous_op", input="{}")
            ],
        ),
    ]
    adapter = ShapeAdapter()
    _, progress, _ = await _drive_collect(adapter, _ScriptedAgent(events), _ask("x"))
    assert "awaiting_confirm" in progress


async def test_exceed_max_iters_maps_to_exceed_max_iters_stage() -> None:
    """ExceedMaxItersEvent -> progress('exceed_max_iters')。"""
    events = [
        ReplyStartEvent(session_id="s", reply_id="r", name="fund_agent"),
        ExceedMaxItersEvent(reply_id="r", name="fund_agent"),
        ReplyEndEvent(session_id="s", reply_id="r"),
    ]
    adapter = ShapeAdapter()
    _, progress, _ = await _drive_collect(adapter, _ScriptedAgent(events), _ask("x"))
    assert "exceed_max_iters" in progress
    assert "done" in progress


# ===========================================================================
# run() 便捷入口 + 回调鲁棒性
# ===========================================================================
async def test_run_returns_final_text_matching_deltas() -> None:
    """run() 消费完 reply_stream，返回拼接出的回复文本（= token 分片拼接）。"""
    model = StreamingScriptedModel(
        [
            _tool_call_step("query_fund_detail", {"question": "005827"}),
            _text_stream_step(["拼接", "文本"]),
        ]
    )
    agent, _ = build_fund_agent(
        model=model, toolkit=_stub_toolkit(), state=_state(), attach_audit=False
    )
    adapter = ShapeAdapter()
    text = await adapter.run(agent, _ask("查 005827"))
    assert text == "拼接文本"


async def test_async_callbacks_supported() -> None:
    """progress_callback / stream_callback 可为 async（iscoroutine 探测）。"""
    progress: list[str] = []
    tokens: list[str] = []

    async def prog(stage: str, **kw: Any) -> None:
        progress.append(stage)

    async def stream(t: str) -> None:
        tokens.append(t)

    adapter = ShapeAdapter(progress_callback=prog, stream_callback=stream)
    await adapter.run(
        _ScriptedAgent(_core_event_sequence()), _ask("x")
    )
    assert "done" in progress
    assert tokens == ["你好", "世界"]


async def test_callback_exception_does_not_break_stream() -> None:
    """回调抛异常被吞掉（best-effort），不阻断主流程（与 run.py _progress 一致）。"""
    def bad_prog(stage: str, **kw: Any) -> None:
        raise RuntimeError("callback boom")

    def bad_stream(t: str) -> None:
        raise RuntimeError("callback boom")

    adapter = ShapeAdapter(progress_callback=bad_prog, stream_callback=bad_stream)
    # 不抛异常、正常消费完事件流
    text = await adapter.run(
        _ScriptedAgent(_core_event_sequence()), _ask("x")
    )
    assert text == "你好世界"


async def test_none_callbacks_safe() -> None:
    """progress_callback / stream_callback 缺省 None 时不报错。"""
    adapter = ShapeAdapter()  # 两个回调都 None
    text = await adapter.run(
        _ScriptedAgent(_core_event_sequence()), _ask("x")
    )
    assert text == "你好世界"


async def test_drive_reusable_across_replies() -> None:
    """同一 ShapeAdapter 实例可跨回合复用（每回合 _reset 清状态）。"""
    adapter = ShapeAdapter()
    agent = _ScriptedAgent(_core_event_sequence())
    await adapter.run(agent, _ask("第一回合"))
    first_final = adapter.final_text
    # 第二回合：model_first_token 标志应被重置 -> 再次发 model_first_token
    progress: list[str] = []
    adapter.progress_callback = lambda stage, **kw: progress.append(stage)
    await adapter.run(agent, _ask("第二回合"))
    assert adapter.final_text == first_final
    assert progress.count("model_first_token") == 1  # 重置后再次发一次
