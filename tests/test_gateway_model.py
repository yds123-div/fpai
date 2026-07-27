# -*- coding: utf-8 -*-
"""T4 #22：GatewayChatModel 行为单测。

验收：
- GatewayChatModel(ChatModelBase) 组合 inner provider，_call_api 委派 + 外层叠熔断
- httpx 回退顺序单测（仅 tools is None 路径回退）
- inner max_retries=0（不与 base 重试叠加）
- llm_chat 的 7 调用者零改动（工厂给 llm_chat stream=False 薄包装，契约不变）
- Opik span 接入点预留（不实装）
- 约束：熔断/超时/fallback 耗尽时抛异常（供 T7 on_model_call 捕）

用 stub inner（ChatModelBase 子类）+ 注入 CircuitBreaker（可控）+ 注入
httpx_post（fake），不连真实模型。

运行：cd backend && python -m pytest -c pyproject.toml ../tests/test_gateway_model.py -v
"""
from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
from agentscope.credential import OpenAICredential
from agentscope.message import Msg, TextBlock
from agentscope.model import (
    ChatModelBase,
    ChatResponse,
    FinishedReason,
    OpenAIChatModel,
)

from model_gateway._circuit import CircuitBreaker, CircuitState
from model_gateway.config import GatewayConfig, LLMConfig
from model_gateway.exceptions import ModelGatewayError, ModelNotConfiguredError
from model_gateway.gateway_model import GatewayChatModel, build_gateway_model
from model_gateway.llm import llm_chat


# ---------------------------------------------------------------------------
# 辅助：stub inner provider + fake httpx
# ---------------------------------------------------------------------------
def _cfg(
    *,
    base_url: str = "http://gateway/v1",
    api_key: str = "k",
    model: str = "qwen3",
) -> GatewayConfig:
    return GatewayConfig(
        llm=LLMConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=0.3,
            max_tokens=100,
            timeout_seconds=30.0,
        ),
        circuit_breaker_threshold=2,
        circuit_breaker_seconds=60.0,
    )


def _text(resp: ChatResponse) -> str:
    return "".join(b.text for b in (resp.content or []) if getattr(b, "text", None))


def _msgs(text: str = "hi") -> list[Msg]:
    return [Msg(name="user", content=[TextBlock(text=text)], role="user")]


class _StubInner(ChatModelBase):
    """stub inner provider：可控成功/失败/流式。"""

    def __init__(
        self,
        *,
        stream: bool = False,
        fail: bool = False,
        response: ChatResponse | None = None,
        stream_chunks: list[ChatResponse] | None = None,
    ) -> None:
        super().__init__(
            credential=OpenAICredential(api_key="stub", base_url="stub"),
            model="stub-model",
            parameters=OpenAIChatModel.Parameters(),
            stream=stream,
            max_retries=0,
        )
        self._fail = fail
        self._response = response
        self._stream_chunks = stream_chunks
        self.call_count = 0
        self.last_tools: Any = "unset"

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        self.call_count += 1
        self.last_tools = tools
        if self._fail:
            raise RuntimeError("inner provider boom")
        if self._response is not None:
            return self._response
        if self.stream and self._stream_chunks is not None:
            async def _gen() -> AsyncGenerator[ChatResponse, None]:
                for c in self._stream_chunks:
                    yield c
            return _gen()
        return ChatResponse(
            content=[TextBlock(text="inner-ok")],
            is_last=True,
            finished_reason=FinishedReason.COMPLETED,
        )


class _FakeResp:
    def __init__(self, data: dict, status: int = 200) -> None:
        self._data = data
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._data


def _fake_post_returning(text: str):
    calls: list[dict] = []

    def _post(url: str, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp({"choices": [{"message": {"content": text}}]})

    _post.calls = calls  # type: ignore[attr-defined]
    return _post


def _fake_post_raising():
    def _post(url: str, json=None, headers=None, timeout=None):
        raise RuntimeError("httpx boom")
    return _post


def _make_gm(
    inner: _StubInner,
    *,
    breaker: CircuitBreaker | None = None,
    httpx_post: Any = None,
    config: GatewayConfig | None = None,
) -> GatewayChatModel:
    return GatewayChatModel(
        inner,
        config=config or _cfg(),
        breaker=breaker or CircuitBreaker("llm", threshold=2, recovery_seconds=60.0),
        httpx_post=httpx_post,
    )


# ---------------------------------------------------------------------------
# 类级 key + max_retries=0
# ---------------------------------------------------------------------------
def test_cb_key_is_llm_class_level() -> None:
    """G1：熔断 key 上移到类。"""
    assert GatewayChatModel._CB_KEY == "llm"


def test_gateway_model_max_retries_is_zero() -> None:
    """inner max_retries=0，不与 base.__call__ 重试叠加（重试归 ModelConfig）。"""
    gm = _make_gm(_StubInner())
    assert gm.max_retries == 0
    assert GatewayChatModel._get_retryable_exceptions() == ()


async def test_base_call_does_not_retry_on_inner_failure() -> None:
    """max_retries=0 + 空 retryable -> base.__call__ 失败时不重试（重试归 ModelConfig）。"""
    inner = _StubInner(fail=True)
    gm = _make_gm(inner, httpx_post=_fake_post_raising())
    with pytest.raises(ModelGatewayError):
        await gm(_msgs())  # 走 __call__（而非直接 _call_api）
    assert inner.call_count == 1  # 只调 1 次，未重试


# ---------------------------------------------------------------------------
# _call_api 委派 inner + 成功记熔断成功
# ---------------------------------------------------------------------------
async def test_call_api_delegates_to_inner_and_returns_response() -> None:
    inner = _StubInner()
    gm = _make_gm(inner)
    res = await gm._call_api("stub-model", _msgs())
    assert inner.call_count == 1
    assert inner.last_tools is None
    assert isinstance(res, ChatResponse)
    assert _text(res) == "inner-ok"


async def test_inner_success_records_breaker_success() -> None:
    breaker = CircuitBreaker("llm", threshold=2, recovery_seconds=60.0)
    breaker.record_failure()  # 预置 1 次失败
    assert breaker.state is CircuitState.CLOSED
    gm = _make_gm(_StubInner(), breaker=breaker)
    await gm._call_api("stub-model", _msgs())
    # 成功清零失败计数（仍 CLOSED，但 failures 归零）
    assert breaker.state is CircuitState.CLOSED
    assert breaker._failures == 0


# ---------------------------------------------------------------------------
# httpx 回退：仅 tools is None 路径
# ---------------------------------------------------------------------------
async def test_inner_failure_no_tools_falls_back_to_httpx() -> None:
    inner = _StubInner(fail=True)
    post = _fake_post_returning("httpx-ok")
    gm = _make_gm(inner, httpx_post=post)
    res = await gm._call_api("stub-model", _msgs())
    assert inner.call_count == 1  # inner 先被调且失败
    assert len(post.calls) == 1  # 走 httpx 回退
    assert post.calls[0]["json"]["model"] == "stub-model"
    assert post.calls[0]["json"]["stream"] is False
    assert _text(res) == "httpx-ok"


async def test_inner_failure_with_tools_does_not_fallback_raises() -> None:
    """agent 带 tools 路径不 httpx 回退；fallback 耗尽抛异常（约束）。"""
    inner = _StubInner(fail=True)
    post = _fake_post_returning("should-not-be-used")
    gm = _make_gm(inner, httpx_post=post)
    with pytest.raises(ModelGatewayError):
        await gm._call_api("stub-model", _msgs(), tools=[{"function": {"name": "f"}}])
    assert len(post.calls) == 0  # tools 非 None -> 不回退


async def test_httpx_not_called_when_inner_succeeds() -> None:
    """回退顺序：inner 成功则 httpx 不被调。"""
    inner = _StubInner(fail=False)
    post = _fake_post_returning("should-not-be-used")
    gm = _make_gm(inner, httpx_post=post)
    await gm._call_api("stub-model", _msgs())
    assert len(post.calls) == 0


async def test_httpx_fallback_failure_raises_gateway_error() -> None:
    """约束：inner 失败 + httpx 也失败 -> 抛 ModelGatewayError（供 T7 捕）。"""
    inner = _StubInner(fail=True)
    gm = _make_gm(inner, httpx_post=_fake_post_raising())
    with pytest.raises(ModelGatewayError):
        await gm._call_api("stub-model", _msgs())


async def test_no_base_url_no_fallback_raises() -> None:
    """无 base_url（如纯 DashScope）时 httpx 回退返回 None -> 抛异常。"""
    inner = _StubInner(fail=True)
    # config 无 base_url
    gm = _make_gm(inner, config=_cfg(base_url="", api_key="k"), httpx_post=_fake_post_returning("x"))
    with pytest.raises(ModelGatewayError):
        await gm._call_api("stub-model", _msgs())


# ---------------------------------------------------------------------------
# 熔断 OPEN 时不调 inner，直接抛
# ---------------------------------------------------------------------------
async def test_circuit_open_raises_without_calling_inner() -> None:
    breaker = CircuitBreaker("llm", threshold=2, recovery_seconds=60.0)
    breaker.record_failure()
    breaker.record_failure()  # -> OPEN
    assert breaker.state is CircuitState.OPEN
    inner = _StubInner()
    gm = _make_gm(inner, breaker=breaker)
    with pytest.raises(ModelGatewayError):
        await gm._call_api("stub-model", _msgs())
    assert inner.call_count == 0  # 熔断打开不调 inner


# ---------------------------------------------------------------------------
# 流式：inner 返回 generator -> _call_api 包 wrapped generator
# ---------------------------------------------------------------------------
async def test_streaming_wraps_generator() -> None:
    chunks = [
        ChatResponse(content=[TextBlock(text="a")], is_last=False),
        ChatResponse(content=[TextBlock(text="b")], is_last=True, finished_reason=FinishedReason.COMPLETED),
    ]
    inner = _StubInner(stream=True, stream_chunks=chunks)
    gm = _make_gm(inner)
    res = await gm._call_api("stub-model", _msgs())
    # 流式返回 async generator（不是 ChatResponse）
    assert not isinstance(res, ChatResponse)
    out = [text async for c in res if (text := _text(c))]
    assert out == ["a", "b"]
    assert inner.call_count == 1


# ---------------------------------------------------------------------------
# Opik span 接入点预留（no-op，不实装）
# ---------------------------------------------------------------------------
async def test_opik_span_hooks_are_noop_and_do_not_raise() -> None:
    gm = _make_gm(_StubInner())
    span = gm._start_opik_span("stub-model", _msgs(), None)
    assert span is None  # 预留占位
    gm._end_opik_span(span)  # 不抛
    gm._end_opik_span(span, error=RuntimeError("x"))  # 不抛


# ---------------------------------------------------------------------------
# llm_chat 薄包装：对外契约不变（签名 + 返回 str）
# ---------------------------------------------------------------------------
async def test_llm_chat_returns_str_via_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """llm_chat 薄包装走 stream=False GatewayChatModel，返回 str。"""
    inner = _StubInner()
    gm = _make_gm(inner)
    monkeypatch.setattr("model_gateway.llm.build_gateway_model", lambda **kw: gm)
    result = llm_chat([{"role": "user", "content": "hi"}])
    assert isinstance(result, str)
    assert result == "inner-ok"
    assert inner.call_count == 1


async def test_llm_chat_passes_enable_thinking_to_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """enable_thinking 透传到 build_gateway_model（薄包装不吞参数）。"""
    captured: dict = {}
    inner = _StubInner()
    gm = _make_gm(inner)

    def _fake_build(**kw):
        captured.update(kw)
        return gm

    monkeypatch.setattr("model_gateway.llm.build_gateway_model", _fake_build)
    llm_chat([{"role": "user", "content": "hi"}], enable_thinking=True)
    assert captured["stream"] is False
    assert captured["enable_thinking"] is True


def test_build_gateway_model_raises_when_not_configured() -> None:
    """无 base_url 且无 api_key -> ModelNotConfiguredError（工厂契约）。"""
    with pytest.raises(ModelNotConfiguredError):
        build_gateway_model(stream=False, config=GatewayConfig())


def test_llm_chat_raises_not_configured_when_no_base_url_no_api_key() -> None:
    """无 base_url 且无 api_key -> llm_chat 抛 ModelNotConfiguredError（契约不变）。"""
    with pytest.raises(ModelNotConfiguredError):
        llm_chat([{"role": "user", "content": "hi"}], config=GatewayConfig())


async def test_llm_chat_propagates_gateway_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """inner 失败 + httpx 失败 -> llm_chat 抛 ModelGatewayError（约束透传）。"""
    inner = _StubInner(fail=True)
    gm = _make_gm(inner, httpx_post=_fake_post_raising())
    monkeypatch.setattr("model_gateway.llm.build_gateway_model", lambda **kw: gm)
    with pytest.raises(ModelGatewayError):
        llm_chat([{"role": "user", "content": "hi"}])
