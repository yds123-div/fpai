# -*- coding: utf-8 -*-
"""T7 (#25)：审计适配层（栅栏 #4，G6/#9 六决策原生重表达）。

把原生 ``ReActAgent`` 事件流桥接到既有 ``audit.append_event`` 持久化契约，
**不动 audit 持久化层**（store.py / ``GET /api/v1/evidence/{answerId}`` 零改动）--
本模块只是一层薄适配：观察 agent 事件 -> 组装两层审计事件 -> 调 ``append_event``。

六决策落位（G6/#9）：

- **D1 混合落点**：``on_reply``（主，消费事件流捕 ``ToolResultEndEvent`` 全状态 +
  ``ExceedMaxItersEvent`` + 最终 ``Msg``）+ ``on_acting``（富细节，ALLOW 工具的
  name/input/result/latency）+ ``on_model_call``（捕模型异常）。
  关键限制：``on_acting`` 只包 ALLOW 权限工具的 I/O 执行，DENIED / validation-ERROR
  不进入此 hook（在 ``_execute_tool_call`` 提前处理）-> 由 ``on_reply`` 补漏。
- **D2 answer_id 线程化**：orchestrator 调 reply 前设 contextvar，middleware 读。
  per-async-task 隔离、共享 agent 无竞态。
- **D3 两层事件**：``tool_call``（per-occurrence，带 state=success/error/denied）
  + ``reply_outcome``（per-reply，outcome = first_pass[不发] / self_healed / partial
  / fallback）。
- **D4 模型异常**：``on_model_call`` try/except -> ``model_call_error``
  per-occurrence（error_type/model_name/attempt），重抛供 agent 重试/兜底。
- **D5 双 middleware**：本类与 ``TracingMiddleware``（OTel/Opik，ADR-0002 暂停 no-op）
  分立两独立 middleware，各自捕获相同事实、解耦（一边挂不影响另一边）。
- **D6 全记 + 去重 + 截断**：每次工具调用都审计（含 SUCCESS，合规需"查了什么"轨迹）；
  ``on_acting`` 记已处理 ``tool_call_id`` set，``on_reply`` 跳过已处理（避免 execution-ERROR
  双发）；input/result 摘要截断到 ``MAX_PAYLOAD_CHARS`` 防胀库。

outcome 判定（D3 四分支漏斗，SI-11）：

| outcome | 判定 |
|---|---|
| ``first_pass`` | 无 tool_call_error、无 ExceedMaxIters、回合正常完成 -> **不发事件** |
| ``self_healed`` | 有 validation-ERROR/DENIED（M4 校验/权限拒，未进 on_acting），回复最终成功 |
| ``partial`` | 有 runtime-ERROR（M5 批次部分失败，经 on_acting），回复完成 |
| ``fallback`` | ``ExceedMaxItersEvent`` 或回合未正常完成（如模型耗尽抛异常）-> #8 兜底 |

约束（D4，T4 #22 已满足）：``GatewayChatModel`` 在熔断/超时/fallback 耗尽时抛异常
（``ModelGatewayError``），本类 ``on_model_call`` 捕获后重抛。
"""
from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable

from agentscope.event import (
    ExceedMaxItersEvent,
    ModelCallEndEvent,
    ReplyEndEvent,
    ToolResultEndEvent,
    ToolResultStartEvent,
)
from agentscope.message import Msg, ToolResultState
from agentscope.middleware import MiddlewareBase
from agentscope.tool import ToolResponse

from pkg.logger import get_logger

logger = get_logger(__name__)

#: input/result 摘要截断上限（D6：防大 payload 胀库）。
MAX_PAYLOAD_CHARS = 500


# ---------------------------------------------------------------------------
# D2：answer_id 线程化（contextvars）
# ---------------------------------------------------------------------------
_audit_answer_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audit_answer_id", default=None
)


def set_audit_answer_id(answer_id: str | None) -> contextvars.Token[str | None]:
    """orchestrator 调 reply 前设当前回合的 answer_id；返回 token 供 reset。"""
    return _audit_answer_id.set(answer_id)


def reset_audit_answer_id(token: contextvars.Token[str | None]) -> None:
    """回复结束后还原 contextvar（配对 set_audit_answer_id）。"""
    _audit_answer_id.reset(token)


def get_audit_answer_id() -> str | None:
    """middleware 读当前回合的 answer_id；未设时返回 None（审计跳过）。"""
    return _audit_answer_id.get()


# ---------------------------------------------------------------------------
# 审计记录（in-memory 镜像，供测试 / 诊断；落库走 append_event）
# ---------------------------------------------------------------------------
@dataclass
class AuditRecord:
    """一条已发的审计事件镜像（event_type + payload + answer_id）。

    与 ``audit_events`` 表行形状一致（answer_id / event_type / payload），
    供测试断言与诊断查看；持久化由 ``append_event`` 完成。
    """

    event_type: str
    payload: dict[str, Any]
    answer_id: str | None = None


def _truncate(text: Any, limit: int = MAX_PAYLOAD_CHARS) -> str:
    """把任意值转成字符串摘要并截断到 limit 字符（D6）。"""
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + "...<truncated>"


def _content_to_text(content: Any) -> str:
    """把 ``ToolResponse.content``（``list[TextBlock]`` / ``str``）拼成纯文本。

    审计只取 result 文本摘要（D6 截断到 ``MAX_PAYLOAD_CHARS``），不解析 JSON--
    结构化取数归属 ``StructuredOutputsCollector``（栅栏 #5），审计与之解耦（D5 精神）。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            getattr(b, "text", "") or "" for b in content if hasattr(b, "text")
        )
    return str(content)


@dataclass
class _ReplyState:
    """单回合的审计中间态（on_reply 开始时重置）。"""

    # tool_call_id -> tool_name（ToolResultStartEvent 拿名，ToolResultEndEvent 拿 state）
    tool_names: dict[str, str] = field(default_factory=dict)
    # on_acting 已处理的 tool_call_id（去重：on_reply 跳过这些）
    handled_ids: set[str] = field(default_factory=set)
    # 错误计数：runtime（经 on_acting，M5）/ validation（on_reply 补漏，M4）
    runtime_errors: int = 0
    validation_errors: int = 0
    exceeded: bool = False
    iter_count: int = 0
    model_call_count: int = 0  # on_model_call 调用序（含失败重试，供 attempt）
    reply_completed: bool = False


class AuditMiddleware(MiddlewareBase):
    """栅栏 #4 审计适配层（G6/#9 D1-D6）。

    三 hook + contextvars answer_id + 两层事件（``tool_call`` per-occurrence /
    ``reply_outcome`` per-reply）+ 去重 + payload 截断。落库走 ``audit.append_event``
    （best-effort，失败仅告警不阻断主流程）；``self.events`` 镜像供测试 / 诊断。

    用法（orchestrator 侧）::

        token = set_audit_answer_id(answer_id)
        try:
            await agent.reply(msg)
        finally:
            reset_audit_answer_id(token)

    无 answer_id（contextvar 未设）时跳过所有落库（延续 SI-11 test 24 语义）。
    """

    def __init__(self) -> None:
        self.events: list[AuditRecord] = []
        self._state = _ReplyState()

    # ------------------------------------------------------------------
    # D1 on_reply：主 hook（消费事件流）
    # ------------------------------------------------------------------
    async def on_reply(  # type: ignore[override]
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        self._state = _ReplyState()  # 每回合重置
        try:
            async for item in next_handler():
                yield item
                self._observe(item)
        finally:
            self._finalize_outcome()

    def _observe(self, item: Any) -> None:
        """观察单个事件，按类型捕状态 / 名 / 计数。"""
        if isinstance(item, ToolResultStartEvent):
            self._state.tool_names[item.tool_call_id] = item.tool_call_name
        elif isinstance(item, ToolResultEndEvent):
            self._on_tool_result_end(item)
        elif isinstance(item, ModelCallEndEvent):
            self._state.iter_count += 1
        elif isinstance(item, ExceedMaxItersEvent):
            self._state.exceeded = True
        elif isinstance(item, Msg):
            # 最终回复 Msg 产出 -> 回合正常完成（含 max_iters 耗尽时兜底 Msg）
            self._state.reply_completed = True
        # ReplyEndEvent 等其它事件不单独置位

    def _on_tool_result_end(self, evt: ToolResultEndEvent) -> None:
        """ToolResultEndEvent：on_acting 未处理过的（validation-ERROR/DENIED）-> on_reply 补发。"""
        if evt.tool_call_id in self._state.handled_ids:
            return  # D6 去重：on_acting 已发 tool_call
        name = self._state.tool_names.get(evt.tool_call_id, "")
        state = str(evt.state.value) if hasattr(evt.state, "value") else str(evt.state)
        self._emit(
            "tool_call",
            {
                "tool_call_id": evt.tool_call_id,
                "tool_name": name,
                "state": state,
                # validation-ERROR/DENIED 未进 on_acting -> 无 input/result/latency 富细节
            },
        )
        if state in ("error", "denied"):
            self._state.validation_errors += 1  # M4 校验/权限拒（self_heal 信号）

    def _finalize_outcome(self) -> None:
        """回合结束：算 outcome，非 first_pass 则发 reply_outcome（D3）。"""
        outcome = self._compute_outcome()
        if outcome == "first_pass":
            return  # D3：first_pass 不发事件
        self._emit(
            "reply_outcome",
            {
                "outcome": outcome,
                "error_count": self._state.runtime_errors
                + self._state.validation_errors,
                "iter_count": self._state.iter_count,
            },
        )

    def _compute_outcome(self) -> str:
        s = self._state
        if s.exceeded or not s.reply_completed:
            return "fallback"
        if s.runtime_errors > 0:
            return "partial"
        if s.validation_errors > 0:
            return "self_healed"
        return "first_pass"

    # ------------------------------------------------------------------
    # D1 on_acting：富细节（ALLOW 工具的 name/input/result/latency）
    # ------------------------------------------------------------------
    async def on_acting(  # type: ignore[override]
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., AsyncGenerator],
    ) -> AsyncGenerator:
        tool_call = input_kwargs["tool_call"]
        tool_name = getattr(tool_call, "name", "")
        tool_call_id = getattr(tool_call, "id", "")
        raw_input = getattr(tool_call, "input", "")
        start = time.perf_counter()
        result_text: str = ""
        state: ToolResultState = ToolResultState.SUCCESS
        async for item in next_handler():
            yield item
            # 末尾 ToolResponse（FunctionTool 经 _convert_func_result_to_chunk 收尾）
            if isinstance(item, ToolResponse):
                state = item.state
                result_text = _content_to_text(getattr(item, "content", None))
        latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
        # D6 去重：标记已处理，on_reply 跳过
        self._state.handled_ids.add(tool_call_id)
        state_str = str(state.value) if hasattr(state, "value") else str(state)
        self._emit(
            "tool_call",
            {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "state": state_str,
                "input": _truncate(raw_input),
                "result": _truncate(result_text),
                "latency_ms": latency_ms,
            },
        )
        if state_str == "error":
            self._state.runtime_errors += 1  # M5 批次部分失败（partial 信号）

    # ------------------------------------------------------------------
    # D4 on_model_call：捕模型异常 -> model_call_error，重抛
    # ------------------------------------------------------------------
    async def on_model_call(  # type: ignore[override]
        self,
        agent: Any,
        input_kwargs: dict,
        next_handler: Callable[..., Any],
    ) -> Any:
        model_name = ""
        cur = input_kwargs.get("current_model")
        if cur is not None:
            model_name = getattr(cur, "model", "") or ""
        attempt = self._state.model_call_count  # 本回合模型调用序（0-based，含重试）
        self._state.model_call_count += 1
        try:
            return await next_handler()
        except Exception as e:
            self._emit(
                "model_call_error",
                {
                    "error_type": type(e).__name__,
                    "error_message": _truncate(str(e)),
                    "model_name": model_name,
                    "attempt": attempt,
                },
            )
            raise  # 重抛：供 agent 重试（ModelConfig）/ 兜底（栅栏 #3）

    # ------------------------------------------------------------------
    # 落库桥接 + 镜像
    # ------------------------------------------------------------------
    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        answer_id = get_audit_answer_id()
        if answer_id is None:
            return  # 无 answer_id 不落审计（SI-11 test 24 语义）
        self.events.append(AuditRecord(event_type, payload, answer_id))
        try:
            from audit import append_event

            append_event(answer_id, event_type, payload)
        except Exception as e:  # 审计落库失败不阻断主流程
            logger.warning("AuditMiddleware append_event 失败: %s", e)
