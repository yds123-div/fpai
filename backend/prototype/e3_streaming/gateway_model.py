# -*- coding: utf-8 -*-
"""E3 原型模型层：最小 GatewayChatModel（G1 决策的薄实现）。

G1（#4）锁定 choke-point = GatewayChatModel(ChatModelBase)，**组合**一个 inner
provider 模型，_call_api 委派 + 外层叠熔断。本文件是原型的最小可跑版本：
- 组合 OpenAIChatModel（有 base_url）或 DashScopeChatModel（仅 api_key）
- stream=True 给 agent / stream=False 给 llm_chat 薄包装（工厂双实例）
- inner max_retries=0，重试归 ModelConfig（G1 决策）
- 熔断：尝试复用 model_gateway._circuit；不可用则 no-op（原型不阻塞）

生产缺口（G1 落地时补）：Opik span、httpx 回退（仅 tools is None）、
熔断 key 上移到类、async 在 agent loop 内跑。
"""
from __future__ import annotations

import os
from typing import Any, AsyncGenerator

from agentscope.model import ChatModelBase, ChatResponse

# 熔断 hook：原型优先复用真实 _circuit，找不到则 no-op
try:  # pragma: no cover - 取决于运行环境
    from model_gateway._circuit import is_open as _cb_is_open
    from model_gateway._circuit import record_failure as _cb_record_failure
    from model_gateway._circuit import record_success as _cb_record_success
    _CB_KEY = "llm"
except Exception:  # noqa: BLE001
    _cb_is_open = None  # type: ignore[assignment]

    def _cb_record_success(*_a: Any, **_k: Any) -> None:  # type: ignore[no-redef]
        pass

    def _cb_record_failure(*_a: Any, **_k: Any) -> None:  # type: ignore[no-redef]
        pass

    _CB_KEY = "llm"


class GatewayChatModel(ChatModelBase):
    """组合式网关模型：_call_api 委派给 inner provider 模型，外层叠熔断。

    G1 决策要点：
    - 不继承 OpenAIChatModel，而是 *组合* 它（按 config 选 OpenAI/DashScope）
    - inner.max_retries=0，避免与 base.__call__ 的重试叠加
    - 流式：inner.stream=self.stream，_call_api 直接转发 inner 的生成器
    """

    def __init__(self, inner: ChatModelBase) -> None:
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

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[type[Exception], ...]:
        # 重试归 agent 的 ModelConfig，这里返回空（base.__call__ 不重试）
        return ()

    async def _call_api(
        self,
        model_name: str,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        **generate_kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        if _cb_is_open is not None and _cb_is_open(_CB_KEY):
            raise RuntimeError("LLM 熔断中（网关关切）")
        res = await self._inner._call_api(
            model_name, messages, tools, tool_choice, **generate_kwargs
        )
        # 非流式：单次 ChatResponse
        if isinstance(res, ChatResponse):
            _cb_record_success(_CB_KEY)
            return res
        # 流式：包一层，仅在生成器正常结束时记成功
        async def _wrapped() -> AsyncGenerator[ChatResponse, None]:
            try:
                async for chunk in res:
                    yield chunk
                _cb_record_success(_CB_KEY)
            except Exception as e:
                _cb_record_failure(_CB_KEY, 5, 60.0)
                raise

        return _wrapped()


def _load_llm_config() -> dict[str, str]:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "").strip(),
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "model": os.getenv("LLM_MODEL", "qwen3").strip() or "qwen3",
    }


def build_gateway_model(*, stream: bool) -> GatewayChatModel:
    """工厂：按 config 选 inner provider，组装 GatewayChatModel。

    G1 决策：stream=True 给 agent；stream=False 给 llm_chat 薄包装。
    """
    cfg = _load_llm_config()
    base_url = cfg["base_url"]
    api_key = cfg["api_key"]
    model = cfg["model"]

    if base_url:
        from agentscope.credential import OpenAICredential
        from agentscope.model import OpenAIChatModel

        inner = OpenAIChatModel(
            credential=OpenAICredential(api_key=api_key or "EMPTY", base_url=base_url),
            model=model,
            parameters=OpenAIChatModel.Parameters(temperature=0.3, max_tokens=1000),
            stream=stream,
            max_retries=0,  # G1：防叠加
            client_kwargs={"timeout": 60.0},
        )
    elif api_key:
        from agentscope.credential import DashScopeCredential
        from agentscope.model import DashScopeChatModel

        inner = DashScopeChatModel(
            credential=DashScopeCredential(api_key=api_key),
            model=model,
            parameters=DashScopeChatModel.Parameters(temperature=0.3, max_tokens=1000),
            stream=stream,
            max_retries=0,
        )
    else:
        raise RuntimeError(
            "未配置 LLM_BASE_URL / LLM_API_KEY；无法构建 GatewayChatModel。"
            "原型可用 --stub 模式跑离线形状验证。"
        )
    return GatewayChatModel(inner=inner)
