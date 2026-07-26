# -*- coding: utf-8 -*-
"""T8 (#26)：ShapeAdapter 流式保形（栅栏 #6，E3/#12 + #17 锁定）。

从 E3 原型（``backend/prototype/e3_streaming/shape_adapter.py``）提升为生产版。
把原生 ``Agent.reply_stream`` 事件流适配为现有 ``progress_callback`` /
``stream_callback`` 契约（**保形**：不改前端 SSE 契约）。

现有契约（栅栏 #6，须保形，见 ``orchestrator/run.py`` / ``api/routes/chat.py``）：

- ``progress_callback(stage: str, **kwargs)`` -- 离散阶段通知
  阶段：``accepted`` / ``thinking`` / ``skill_fetching`` / ``llm_generating`` /
        ``model_first_token`` / ``done`` / ``awaiting_confirm`` / ``exceed_max_iters``
- ``stream_callback(token_text: str)`` -- token 级文本增量
- ``show_thinking=True`` 时透传 ``<think>...</think>`` 推理块；``False`` 时剥离

原生事件 -> 现有契约 映射表（E3 已验）：

  ``ReplyStartEvent``          -> ``progress("thinking")``
  ``ToolCallStartEvent``       -> ``progress("skill_fetching", tool=...)``  [reset_tools 噪音过滤]
  ``ToolResultStartEvent``     -> ``progress("skill_fetching", tool=..., phase="result")``  [同上]
  ``ModelCallStartEvent``      -> ``progress("llm_generating")``
  ``TextBlockDeltaEvent``      -> 首个 -> ``progress("model_first_token")``；每个 -> ``stream_callback(delta)``
  ``ThinkingBlockStartEvent``  -> ``show_thinking`` 时 ``stream_callback("<think>")``
  ``ThinkingBlockDeltaEvent``  -> ``show_thinking`` 时 ``stream_callback(delta)``；否则丢弃
  ``ThinkingBlockEndEvent``    -> ``show_thinking`` 时 ``stream_callback("</think>")``
  ``ReplyEndEvent``            -> ``progress("done")``
  ``RequireUserConfirmEvent``  -> ``progress("awaiting_confirm")``（HITL 暂停）
  ``ExceedMaxItersEvent``      -> ``progress("exceed_max_iters")``

保形要点：

- **首个 token 先发 model_first_token 进度**（复刻 ``run.py`` ``_stream_with_ttft``）。
- **``<think>`` 透传/剥离**：原生已把推理分离到 ``ThinkingBlock`` 事件时，按
  ``show_thinking`` 透传或丢弃；provider 未分离、把 ``<think>`` 内联在 text 里时，
  ``_ThinkFilter`` 状态机兜底剥离（``show_thinking=False``）。双 provider
  （OpenAI 兼容 / DashScope）保形（E3 已验：68 token 分片 + 5 核心阶段全命中；
  DashScope 核心 5 阶段全命中、token 级流式、``<think>`` 透传）。
- **``reset_tools`` 噪音过滤**：``Toolkit`` 自带的 meta 工具 ``reset_tools``（agent
  自管理工具组激活/停用）不映射为 ``skill_fetching`` 进度，前端不收到脏事件
  （spec #18 栅栏 #6）。``NOISE_TOOL_NAMES`` 为待扩展的噪音工具白名单。
- 回调可同步/异步（``iscoroutine`` 探测）；回调抛异常不阻断主流程（best-effort）。

主 seam ``run_chat_turn_async`` 接线在 T10；本工单提供 ``ShapeAdapter`` 供其调用。
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Callable

from agentscope.agent import Agent
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
from agentscope.message import Msg

#: 推理块开/闭标签（与 ``orchestrator/run.py`` ``_strip_think_blocks`` 一致）。
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"

#: SSE 层须过滤的噪音工具名（spec #18 栅栏 #6：前端不收到脏事件）。
#:
#: ``reset_tools`` 是 ``Toolkit`` 自带 meta 工具（agent 自管理工具组激活/停用），
#: 非业务取数，其 ``ToolCallStartEvent`` / ``ToolResultStartEvent`` 不映射为
#: ``skill_fetching`` 进度。将来若新增其它内部 meta 工具，在此追加。
NOISE_TOOL_NAMES: frozenset[str] = frozenset({"reset_tools"})

#: E3 原型验收的 5 核心阶段（不含起始 ``accepted`` 与终止 ``done`` 之外的衍生阶段）。
CORE_STAGES: frozenset[str] = frozenset(
    {"accepted", "thinking", "skill_fetching", "llm_generating",
     "model_first_token", "done"}
)


class _ThinkFilter:
    """``<think>...</think>`` 状态机（从 ``llm_chat_stream`` 移植）。

    用于 provider 未分离推理、把 ``<think>`` 内联在 text content 里的兜底情形
    （``show_thinking=False`` 时剥离）。原生 ``ThinkingBlockDeltaEvent`` 路径下
    不需要本类（原生已分离，直接丢弃即可）。
    """

    def __init__(self) -> None:
        self.in_think = False
        self.carry = ""

    def feed(self, delta: str) -> str:
        """喂一个 text delta，返回剥离 ``<think>...</think>`` 后的可见文本。

        跨 delta 的未闭合 ``<think>`` / ``</think>`` 用 ``carry`` 拼接续接。
        """
        if not delta:
            return ""
        s = self.carry + delta
        self.carry = ""
        out: list[str] = []
        i = 0
        while i < len(s):
            if not self.in_think:
                j = s.find(_THINK_OPEN, i)
                if j == -1:
                    # 末尾可能是未闭合 ``<think`` 前缀，carry 续接
                    safe = self._rstrip_partial(s, i, _THINK_OPEN)
                    out.append(safe[0])
                    self.carry = safe[1]
                    break
                out.append(s[i:j])
                self.in_think = True
                i = j + len(_THINK_OPEN)
            else:
                k = s.find(_THINK_CLOSE, i)
                if k == -1:
                    # 仍在 think 内，整段丢弃但保留可能未闭合的 ``</think`` 前缀
                    self.carry = self._partial_suffix(s, i, _THINK_CLOSE)
                    break
                self.in_think = False
                i = k + len(_THINK_CLOSE)
        return "".join(out)

    @staticmethod
    def _partial_suffix(s: str, start: int, marker: str) -> str:
        """返回 ``s[start:]`` 末尾可能是 ``marker`` 前缀的子串（供下个 delta 续接）。"""
        tail = s[start:]
        for n in range(min(len(marker) - 1, len(tail)), 0, -1):
            if tail.endswith(marker[:n]):
                return tail[-n:]
        return ""

    @staticmethod
    def _rstrip_partial(s: str, start: int, marker: str) -> tuple[str, str]:
        """把 ``s[start:]`` 末尾的 ``marker`` 前缀拆出来：(可见, carry)。"""
        tail = s[start:]
        for n in range(min(len(marker) - 1, len(tail)), 0, -1):
            if tail.endswith(marker[:n]):
                return tail[: -n], tail[-n:]
        return tail, ""


class ShapeAdapter:
    """把 ``Agent.reply_stream`` 事件流适配为现有 ``progress``/``stream`` 回调契约。

    保形（栅栏 #6）：5 核心阶段全命中 + token 分片 + ``<think>`` 透传/剥离 +
    ``reset_tools`` 噪音过滤 + 双 provider（OpenAI 兼容 / DashScope）保形。

    用法（orchestrator 侧，T10 接线）::

        adapter = ShapeAdapter(
            progress_callback=progress_cb,
            stream_callback=stream_cb,
            show_thinking=show_thinking,
        )
        final_text = await adapter.run(agent, user_msg)
        # 或观察事件序列：
        async for kind, detail in adapter.drive(agent, user_msg):
            ...

    回调可同步或异步（``iscoroutine`` 探测）；回调抛异常被吞掉（best-effort，
    不阻断主流程），与 ``orchestrator/run.py`` ``_progress`` / ``_stream_with_ttft``
    行为一致。
    """

    def __init__(
        self,
        *,
        progress_callback: Callable[..., Any] | None = None,
        stream_callback: Callable[[str], Any] | None = None,
        show_thinking: bool = False,
    ) -> None:
        self.progress_callback = progress_callback
        self.stream_callback = stream_callback
        self.show_thinking = show_thinking
        self._first_token_seen = False
        self._text_filter = _ThinkFilter()  # 仅 provider 内联 <think> 时生效
        self._accumulated: list[str] = []
        #: 回复最终文本（``drive``/``run`` 完整消费后可用）。
        self.final_text: str = ""

    # ------------------------------------------------------------------
    # 回调封装（同步/异步兼容 + best-effort 吞异常）
    # ------------------------------------------------------------------
    async def _progress(self, stage: str, **kwargs: Any) -> None:
        if self.progress_callback is None:
            return
        try:
            out = self.progress_callback(stage, **kwargs)
            if asyncio.iscoroutine(out):
                await out
        except Exception:
            return  # 回调失败不阻断主流程

    async def _stream(self, token: str) -> None:
        if not token or self.stream_callback is None:
            return
        try:
            out = self.stream_callback(token)
            if asyncio.iscoroutine(out):
                await out
        except Exception:
            return

    async def _emit_token(
        self, token: str
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式吐一个 token：首个时先发 ``model_first_token`` 进度。

        yield ``(kind, detail)``：首个 token 先 yield 一次
        ``("progress", "model_first_token")``，再 yield ``("token", token)``。
        后续 token 只 yield ``("token", token)``。同时把 token 透传给
        ``stream_callback`` 并累加进 ``final_text``。
        """
        if not token:
            return
        if not self._first_token_seen:
            self._first_token_seen = True
            await self._progress("model_first_token")
            yield ("progress", "model_first_token")
        self._accumulated.append(token)
        await self._stream(token)
        yield ("token", token)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    async def drive(
        self, agent: Agent, user_input: Msg
    ) -> AsyncGenerator[tuple[str, str], None]:
        """驱动 ``reply_stream``，把事件映射为 ``progress``/``stream`` 回调。

        yield ``(kind, detail)`` 供观察：``kind ∈ {"progress", "token"}``，
        ``detail`` 为 stage 名或 token 文本。``drive`` 内部已把事件透传给回调，
        故观察者无需重复转发。完整消费后 ``self.final_text`` 为拼接出的回复文本。
        """
        self._reset()
        await self._progress("accepted")
        yield ("progress", "accepted")

        async for event in agent.reply_stream(user_input):
            # ---- 进度阶段映射 ----
            if isinstance(event, ReplyStartEvent):
                await self._progress("thinking")
                yield ("progress", "thinking")

            elif isinstance(event, ToolCallStartEvent):
                if event.tool_call_name in NOISE_TOOL_NAMES:
                    continue  # reset_tools 噪音过滤（前端不收到脏事件）
                await self._progress(
                    "skill_fetching", tool=event.tool_call_name
                )
                yield ("progress", f"skill_fetching:{event.tool_call_name}")

            elif isinstance(event, ToolResultStartEvent):
                if event.tool_call_name in NOISE_TOOL_NAMES:
                    continue
                await self._progress(
                    "skill_fetching",
                    tool=event.tool_call_name,
                    phase="result",
                )
                yield ("progress", f"skill_result:{event.tool_call_name}")

            elif isinstance(event, ModelCallStartEvent):
                await self._progress("llm_generating")
                yield ("progress", "llm_generating")

            # ---- token 级流式映射 ----
            elif isinstance(event, TextBlockDeltaEvent):
                delta = event.delta or ""
                # provider 未分离推理时，<think> 可能内联在 text 里
                if not self.show_thinking:
                    delta = self._text_filter.feed(delta)
                if delta:
                    async for item in self._emit_token(delta):
                        yield item

            elif isinstance(event, ThinkingBlockStartEvent):
                # 原生已分离推理：show_thinking 时在开始处发一次 <think>
                if self.show_thinking:
                    async for item in self._emit_token(_THINK_OPEN):
                        yield item

            elif isinstance(event, ThinkingBlockDeltaEvent):
                # show_thinking 时透传原始 delta；否则丢弃（原生已分离，无需状态机）
                if self.show_thinking:
                    async for item in self._emit_token(event.delta or ""):
                        yield item

            elif isinstance(event, ThinkingBlockEndEvent):
                if self.show_thinking:
                    async for item in self._emit_token(_THINK_CLOSE):
                        yield item

            # ---- 终止/暂停映射 ----
            elif isinstance(event, ReplyEndEvent):
                await self._progress("done")
                yield ("progress", "done")

            elif isinstance(event, RequireUserConfirmEvent):
                # HITL 暂停：现有契约无直接对应，映射为 awaiting_confirm
                await self._progress("awaiting_confirm")
                yield ("progress", "awaiting_confirm")

            elif isinstance(event, ExceedMaxItersEvent):
                await self._progress("exceed_max_iters")
                yield ("progress", "exceed_max_iters")

        self.final_text = "".join(self._accumulated)

    async def run(self, agent: Agent, user_input: Msg) -> str:
        """驱动 ``reply_stream`` 并消费完毕，返回拼接出的回复文本。

        供 orchestrator（T10）使用：只关心回调被触发 + 最终文本，不观察事件序列。
        """
        async for _ in self.drive(agent, user_input):
            pass
        return self.final_text

    def _reset(self) -> None:
        """每回合重置内部态（``drive`` 开始时调）。"""
        self._first_token_seen = False
        self._text_filter = _ThinkFilter()
        self._accumulated = []
        self.final_text = ""
