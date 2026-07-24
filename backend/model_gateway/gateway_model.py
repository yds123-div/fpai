# -*- coding: utf-8 -*-
"""T4 #22：GatewayChatModel 生产实现（模型 choke-point，G1 决策）。

从 E3 原型（``backend/prototype/e3_streaming/gateway_model.py``）提升为生产版。
组合一个 inner provider 模型（``OpenAIChatModel``[有 base_url] /
``DashScopeChatModel``[仅 api_key] 按 config 选），**不继承**它。

``_call_api`` 委派 inner provider + 外层叠加：
- 三态熔断（``CircuitBreaker``，key="llm" 类级；G1 决策：key 上移到类）
- httpx 直连回退（仅 ``tools is None`` 路径；agent 带 tools 时不回退）
- Opik span 预留接入点（ADR-0002 暂停，本工单只预留不实装）

工厂双实例：``stream=True`` 给 agent / ``stream=False`` 给 ``llm_chat`` 薄包装
（7 调用者零改动）。inner ``max_retries=0``（重试归属 agent 层 ``ModelConfig``）；
``async`` 在 agent loop 内跑，解 contextvars/线程池痛点。

约束（栅栏 #4 依赖）：``GatewayChatModel`` 须在熔断/超时/fallback 耗尽时
**抛异常**（供 T7 ``on_model_call`` 捕），不静默返回空。
"""
from __future__ import annotations

import re
from typing import Any, AsyncGenerator

from agentscope.message import Msg, TextBlock
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason

from model_gateway._circuit import CircuitBreaker
from model_gateway.config import GatewayConfig, load_gateway_config
from model_gateway.exceptions import ModelGatewayError, ModelNotConfiguredError
from pkg.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Msg <-> dict 转换（llm_chat 薄包装传 list[dict]，ChatModelBase 要 list[Msg]）
# ---------------------------------------------------------------------------
def _dicts_to_msgs(messages: list[dict[str, Any]]) -> list[Msg]:
    """OpenAI 风格 dict 列表 -> AgentScope Msg 列表。

    ``llm_chat`` 对外契约是 ``list[dict]``（role/content）；ChatModelBase.__call__
    要 ``list[Msg]``。本函数在薄包装内部转换，对外契约不变。
    """
    out: list[Msg] = []
    for d in messages:
        role = d.get("role", "user")
        if role not in ("user", "assistant", "system"):
            role = "user"  # 容错：非标准 role（如 tool）归 user
        content = d.get("content", "")
        if isinstance(content, str):
            blocks: list[Any] = [TextBlock(text=content)] if content else []
        elif isinstance(content, list):
            blocks = content  # 假设已是 ContentBlock 列表
        else:
            blocks = [TextBlock(text=str(content))]
        name = d.get("name") or role
        out.append(Msg(name=name, content=blocks, role=role))
    return out


def _msgs_to_dicts(messages: list[Msg]) -> list[dict[str, str]]:
    """AgentScope Msg 列表 -> OpenAI 风格 dict 列表（httpx 回退用）。"""
    out: list[dict[str, str]] = []
    for m in messages:
        parts = []
        for b in m.content or []:
            text = getattr(b, "text", None)
            if text:
                parts.append(text)
        out.append({"role": m.role, "content": "\n".join(parts)})
    return out


class GatewayChatModel(ChatModelBase):
    """组合式网关模型（G1 决策的 choke-point）。

    不继承 inner provider，而是 *组合* 它（按 config 选 OpenAI/DashScope）。
    ``_call_api`` 委派 inner，外层叠熔断/httpx 回退/Opik span 预留。

    G1 决策要点：
    - inner.max_retries=0，避免与 base.__call__ 的重试叠加（重试归 ModelConfig）
    - 熔断 key="llm" 上移到类（``_CB_KEY``），三态 CircuitBreaker
    - httpx 回退仅 ``tools is None`` 路径（agent 带 tools 时不回退）
    - Opik span 预留接入点（no-op，ADR-0002 恢复时实装）
    """

    _CB_KEY = "llm"  # G1：熔断 key 上移到类

    def __init__(
        self,
        inner: ChatModelBase,
        *,
        config: GatewayConfig,
        enable_thinking: bool = False,
        breaker: CircuitBreaker | None = None,
        httpx_post: Any | None = None,
    ) -> None:
        """初始化网关模型。

        Args:
            inner: 被组合的 inner provider 模型（已 max_retries=0）。
            config: 网关配置（熔断阈值/冷却 + httpx 回退用的 base_url/api_key/model）。
            enable_thinking: 是否启用推理（透传给 inner Parameters，已由工厂设置）。
            breaker: 熔断器（测试可注入可控时钟的实例；生产 None -> 按 config 新建）。
            httpx_post: httpx 回退的 POST 函数（测试注入；生产 None -> 用 ``httpx.post``）。
        """
        super().__init__(
            credential=inner.credential,
            model=inner.model,
            parameters=inner.parameters,
            stream=inner.stream,
            max_retries=0,  # G1：inner 不重试，重试归 ModelConfig
            retry_delay=inner.retry_delay,
            context_size=inner.context_size,
        )
        self._inner = inner
        self._config = config
        self._enable_thinking = enable_thinking
        self._breaker = breaker or CircuitBreaker(
            self._CB_KEY,
            threshold=config.circuit_breaker_threshold,
            recovery_seconds=config.circuit_breaker_seconds,
        )
        self._httpx_post = httpx_post  # 生产 None -> 懒加载 httpx.post

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[type[Exception], ...]:
        # 重试归 agent 层 ModelConfig；base.__call__ 不在此重试
        return ()

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        # 1. 熔断：OPEN 时直接抛（不调 inner）——约束：抛异常不静默
        if self._breaker.is_open():
            raise ModelGatewayError("LLM 熔断中（网关关切）")

        # 2. Opik span 预留接入点（ADR-0002 暂停，no-op）
        span = self._start_opik_span(model_name, messages, tools)

        try:
            res = await self._inner._call_api(
                model_name, messages, tools, tool_choice, **generate_kwargs
            )
        except Exception as e:
            self._breaker.record_failure()
            self._end_opik_span(span, error=e)
            logger.warning("inner provider 调用失败，尝试 httpx 回退: %s", e)
            # httpx 回退：仅 tools is None 路径（agent 带 tools 时不回退）
            if tools is None:
                fallback = await self._httpx_fallback(model_name, messages)
                if fallback is not None:
                    self._breaker.record_success()
                    self._end_opik_span(span, response=fallback)
                    return fallback
            # 约束（栅栏 #4）：fallback 耗尽时抛异常，供 T7 on_model_call 捕
            raise ModelGatewayError(f"LLM 调用失败且无可用回退: {e}") from e

        # inner 成功
        if isinstance(res, ChatResponse):
            self._breaker.record_success()
            self._end_opik_span(span, response=res)
            return res

        # 流式：包一层，仅在生成器正常结束时记成功
        async def _wrapped() -> AsyncGenerator[ChatResponse, None]:
            try:
                async for chunk in res:
                    yield chunk
                self._breaker.record_success()
                self._end_opik_span(span)
            except Exception as e:
                self._breaker.record_failure()
                self._end_opik_span(span, error=e)
                raise

        return _wrapped()

    # --- Opik span 预留（ADR-0002 暂停，no-op；恢复时在此挂 LLM span）---
    def _start_opik_span(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None,
    ) -> Any:
        """预留：ADR-0002 恢复时在此开结构化 LLM span
        （model/messages/tools/latency）。现为 no-op，返回占位。"""
        return None

    def _end_opik_span(
        self,
        span: Any,
        response: ChatResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        """预留：ADR-0002 恢复时在此关 span（记 output/usage/error）。

        contextvars 注意（ADR-0002 决策 2）：``llm_chat`` 薄包装路径在
        ThreadPoolExecutor 工作线程内调用本方法，span 生命周期应在主线程
        包裹工作线程；agent 路径在 async loop 内直接调用，contextvars 正常。
        恢复实装时按 ADR-0002 处理此差异。
        """
        pass

    async def _httpx_fallback(
        self,
        model_name: str,
        messages: list[Msg],
    ) -> ChatResponse | None:
        """httpx 直连回退（仅 tools is None 路径，inner 失败时）。

        用 config.llm 的 base_url/api_key/model 直连 OpenAI 兼容
        ``/chat/completions``。无 base_url（如纯 DashScope）时返回 None，
        由调用方抛异常。

        生产用 ``httpx.post``；测试可注入 ``httpx_post`` 返回假响应。
        """
        llm = self._config.llm
        bu = (llm.base_url or "").strip()
        if not bu:
            return None  # 无 base_url 无法 httpx 回退
        # 规范化 URL：未以 /v<N> 结尾则补 /v1
        if not re.search(r"/v\d+$", bu.rstrip("/")):
            bu = bu.rstrip("/") + "/v1"
        url = bu.rstrip("/") + "/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if (llm.api_key or "").strip():
            headers["Authorization"] = f"Bearer {llm.api_key.strip()}"
        payload: dict[str, Any] = {
            "model": (model_name or llm.model or "").strip() or "qwen3",
            "messages": _msgs_to_dicts(messages),
            "max_tokens": llm.max_tokens,
            "temperature": llm.temperature,
            "stream": False,
        }
        post = self._httpx_post
        if post is None:
            import httpx as _httpx

            post = _httpx.post
        try:
            resp = post(url, json=payload, headers=headers, timeout=llm.timeout_seconds)
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("httpx 回退失败: %s", e)
            return None  # 回退失败 -> 调用方抛 ModelGatewayError（约束）
        choices = data.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "") or ""
        return ChatResponse(
            content=[TextBlock(text=content)],
            is_last=True,
            finished_reason=FinishedReason.COMPLETED,
        )


def build_gateway_model(
    *,
    stream: bool,
    config: GatewayConfig | None = None,
    enable_thinking: bool = False,
) -> GatewayChatModel:
    """工厂：按 config 选 inner provider，组装 GatewayChatModel。

    G1 决策：``stream=True`` 给 agent；``stream=False`` 给 ``llm_chat`` 薄包装。
    inner 一律 ``max_retries=0``（防与 base 重试叠加，重试归 ``ModelConfig``）。
    enable_thinking 透传到 inner ``Parameters.thinking_enable``。

    无 base_url 且无 api_key 时抛 ``ModelNotConfiguredError``。
    """
    cfg = config or load_gateway_config()
    llm = cfg.llm
    base_url = (llm.base_url or "").strip()
    api_key = (llm.api_key or "").strip()
    model = (llm.model or "").strip() or "qwen3"
    max_tokens = llm.max_tokens or None  # Parameters 要求 gt=0；0 或空传 None

    if base_url:
        from agentscope.credential import OpenAICredential
        from agentscope.model import OpenAIChatModel

        inner = OpenAIChatModel(
            credential=OpenAICredential(api_key=api_key or "EMPTY", base_url=base_url),
            model=model,
            parameters=OpenAIChatModel.Parameters(
                temperature=llm.temperature,
                max_tokens=max_tokens,
                thinking_enable=bool(enable_thinking),
            ),
            stream=stream,
            max_retries=0,  # G1：防叠加
            client_kwargs={"timeout": llm.timeout_seconds},
        )
    elif api_key:
        from agentscope.credential import DashScopeCredential
        from agentscope.model import DashScopeChatModel

        inner = DashScopeChatModel(
            credential=DashScopeCredential(api_key=api_key),
            model=model,
            parameters=DashScopeChatModel.Parameters(
                temperature=llm.temperature,
                max_tokens=max_tokens,
                thinking_enable=bool(enable_thinking),
            ),
            stream=stream,
            max_retries=0,
        )
    else:
        raise ModelNotConfiguredError(
            "LLM_BASE_URL 与 LLM_API_KEY 均未配置，无法构建 GatewayChatModel"
        )
    return GatewayChatModel(
        inner, config=cfg, enable_thinking=enable_thinking
    )
