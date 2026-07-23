# -*- coding: utf-8 -*-
"""E3 原型核心：原生 reply_stream 事件 -> 现有 progress_callback / stream_callback 保形映射。

现有契约（栅栏 #6，须保形）：
- progress_callback(stage: str, **kwargs)  —— 离散阶段通知
  阶段：accepted / thinking / skill_fetching / llm_generating / model_first_token / done
- stream_callback(token_text: str)         —— token 级文本增量
- show_thinking=True 时透传 <think>...</think>；False 时剥离

原生事件 -> 现有契约 的映射表（验证目标）：
  ReplyStartEvent          -> progress("thinking")
  ToolCallStartEvent       -> progress("skill_fetching", tool=...)
  ModelCallStartEvent      -> progress("llm_generating")
  TextBlockDeltaEvent      -> 首个 -> progress("model_first_token")；每个 -> stream_callback(delta)
  ThinkingBlockDeltaEvent  -> show_thinking 时 stream_callback("<think>delta</think>")；否则丢弃
  ReplyEndEvent            -> progress("done")
  RequireUserConfirmEvent  -> progress("awaiting_confirm")（HITL 暂停）
  ExceedMaxItersEvent      -> progress("exceed_max_iters")
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


class _ThinkFilter:
    """<think>...</think> 状态机（从 llm_chat_stream 移植），用于 provider
    未分离推理、把 <think> 内联在 content 里的兜底情形。

    原生 ThinkingBlockDeltaEvent 路径下不需要本类。
    """

    def __init__(self) -> None:
        self.in_think = False
        self.carry = ""

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        s = self.carry + delta
        self.carry = ""
        out: list[str] = []
        i = 0
        while i < len(s):
            if not self.in_think:
                j = s.find("<think>", i)
                if j == -1:
                    out.append(s[i:])
                    break
                out.append(s[i:j])
                self.in_think = True
                i = j + len("<think>")
            else:
                k = s.find("</think>", i)
                if k == -1:
                    break
                self.in_think = False
                i = k + len("</think>")
        return "".join(out)


class ShapeAdapter:
    """把 Agent.reply_stream 的事件流适配为现有 progress/stream 回调契约。"""

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
        self._text_filter = _ThinkFilter()  # 仅当 provider 内联 <think> 时生效

    async def _progress(self, stage: str, **kwargs: Any) -> None:
        if self.progress_callback is None:
            return
        try:
            out = self.progress_callback(stage, **kwargs)
            if asyncio.iscoroutine(out):
                await out
        except Exception:
            return

    async def _stream(self, token: str) -> None:
        if not token or self.stream_callback is None:
            return
        try:
            out = self.stream_callback(token)
            if asyncio.iscoroutine(out):
                await out
        except Exception:
            return

    async def _emit_token(self, token: str) -> AsyncGenerator[tuple[str, str], None]:
        """流式吐一个 token：首个时先发 model_first_token 进度。

        yield (kind, detail)：首个 token 先 yield 一次 ("progress","model_first_token")，
        再 yield ("token", token)。后续只 yield token。
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

    async def drive(self, agent: Agent, user_input: Msg) -> AsyncGenerator[tuple[str, str], None]:
        """驱动 reply_stream，yield (kind, detail) 供观察；返回 None。

        kind ∈ {"progress", "token"}；detail 为 stage 或 token 文本。
        同时把 token/progress 透传给回调，复刻现有契约。
        """
        self._accumulated: list[str] = []
        await self._progress("accepted")
        yield ("progress", "accepted")

        async for event in agent.reply_stream(user_input):
            # ---- 进度阶段映射 ----
            if isinstance(event, ReplyStartEvent):
                await self._progress("thinking")
                yield ("progress", "thinking")

            elif isinstance(event, ToolCallStartEvent):
                await self._progress("skill_fetching", tool=event.tool_call_name)
                yield ("progress", f"skill_fetching:{event.tool_call_name}")

            elif isinstance(event, ToolResultStartEvent):
                await self._progress("skill_fetching", tool=event.tool_call_name, phase="result")
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
                # show_thinking：在开始处发一次 <think>（而非每个 delta 包一次）
                if self.show_thinking:
                    async for item in self._emit_token("<think>"):
                        yield item

            elif isinstance(event, ThinkingBlockDeltaEvent):
                # 原生已把推理分离到独立通道：show_thinking 时透传原始 delta
                if self.show_thinking:
                    async for item in self._emit_token(event.delta or ""):
                        yield item
                # show_thinking=False 时直接丢弃（原生已分离，无需状态机过滤）

            elif isinstance(event, ThinkingBlockEndEvent):
                if self.show_thinking:
                    async for item in self._emit_token("</think>"):
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
