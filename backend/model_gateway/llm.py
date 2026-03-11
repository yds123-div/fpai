"""
LLM 统一调用：优先通过 AgentScope（OpenAIChatModel/DashScopeChatModel）调用。
超时与熔断由 gateway 层统一处理。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
from typing import Any

from model_gateway.config import GatewayConfig, load_gateway_config, LLMConfig
from model_gateway._circuit import is_open, record_failure, record_success
from pkg.logger import get_logger
logger = get_logger(__name__)
try:
    from agentscope.model import OpenAIChatModel, DashScopeChatModel
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    OpenAIChatModel = None  # type: ignore[misc, assignment]
    DashScopeChatModel = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False


class ModelGatewayError(Exception):
    """模型网关调用异常。"""
    pass


class ModelNotConfiguredError(ModelGatewayError):
    """未配置模型地址。"""
    pass


def _create_agentscope_model(llm: LLMConfig):
    """根据 config 创建 AgentScope ChatModel（与 routing/faq 逻辑一致）。"""
    if not _AGENTSCOPE_AVAILABLE or (OpenAIChatModel is None and DashScopeChatModel is None):
        return None
    base_url = (llm.base_url or "").strip()
    api_key = (llm.api_key or "").strip()
    gen = {"temperature": llm.temperature, "max_tokens": llm.max_tokens}
    if base_url:
        return OpenAIChatModel(
            model_name=llm.model or "qwen3-32b",
            api_key=api_key or None,
            stream=False,
            client_kwargs={"base_url": base_url},
            generate_kwargs=gen,
            enable_thinking=False,
        )
    if api_key:
        return DashScopeChatModel(
            model_name=llm.model or "qwen3-32b",
            api_key=api_key,
            stream=False,
            generate_kwargs=gen,
            enable_thinking=False,
        )
    return None


def _content_from_chat_response(response: Any) -> str:
    """从 AgentScope ChatResponse 中取出首段文本内容。"""
    if response is None:
        return ""
    content = getattr(response, "content", None) or []
    parts = []
    for block in content:
        if hasattr(block, "text"):
            parts.append(block.text or "")
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", "") or "")
    return "\n".join(parts).strip()


async def _chat_via_agentscope(model: Any, messages: list[dict]) -> str:
    """通过 AgentScope 模型调用（async 内部）；创建时已用 stream=False，响应为单次结果。"""
    logger.info(f"通过 AgentScope 模型调用：{model}")
    logger.info(f"通过 AgentScope 模型调用：messages：{messages}")
    resp = await model(messages)
    logger.info(f"通过 AgentScope 模型调用：resp：{resp}")
    # 本网关统一 stream=False，不按流式消费，避免 DashScope 返回对象带 __aiter__ 却非真流导致异常
    return _content_from_chat_response(resp)


def _run_agentscope_in_new_loop(model: Any, messages: list[dict]) -> str:
    """在独立事件循环中运行 _chat_via_agentscope（用于线程内调用，避免与主循环冲突）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_chat_via_agentscope(model, messages))
    finally:
        loop.close()


def llm_chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    config: GatewayConfig | None = None,
) -> str:
    """
    调用 LLM 对话接口：优先通过 AgentScope（OpenAIChatModel/DashScopeChatModel）调用；
    未安装或未配置 AgentScope 时回退到 httpx 直连。未配置任何可用方式时抛出 ModelNotConfiguredError。
    支持熔断：key 为 "llm"。
    """
    cfg = config or load_gateway_config()
    llm = cfg.llm
    key = "llm"
    if is_open(key):
        raise ModelGatewayError("LLM 熔断中，请稍后重试")
    agentscope_model = _create_agentscope_model(llm)
    if agentscope_model is not None:
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            else:
                running_loop = True
            if running_loop is None:
                content = asyncio.run(_chat_via_agentscope(agentscope_model, messages))
            else:
                # 已在事件循环中（如 FastAPI 异步请求）：在线程内新建 loop 执行，避免 asyncio.run() 报错
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    content = pool.submit(
                        _run_agentscope_in_new_loop, agentscope_model, messages
                    ).result()
            record_success(key)
            return content or ""
        except Exception as e:
            record_failure(key, cfg.circuit_breaker_threshold, cfg.circuit_breaker_seconds)
            if isinstance(e, ModelGatewayError):
                raise
            raise ModelGatewayError(f"LLM 调用失败: {e}") from e
    raise ModelNotConfiguredError("LLM_BASE_URL 未配置且无可用的 AgentScope 模型配置")
