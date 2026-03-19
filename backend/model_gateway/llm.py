"""
LLM 统一调用：优先通过 AgentScope（OpenAIChatModel/DashScopeChatModel）调用。
超时与熔断由 gateway 层统一处理。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
from typing import Any, AsyncGenerator

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
    base_url: str | None = None,
    api_key: str | None = None,
    config: GatewayConfig | None = None,
) -> str:
    """
    调用 LLM 对话接口：优先通过 AgentScope（OpenAIChatModel/DashScopeChatModel）调用；
    未安装或未配置 AgentScope 时回退到 httpx 直连。未配置任何可用方式时抛出 ModelNotConfiguredError。
    支持熔断：key 为 "llm"。
    """
    cfg = config or load_gateway_config()
    if model:
        cfg.llm.model = model
    if base_url is not None:
        cfg.llm.base_url = base_url
    if api_key is not None:
        cfg.llm.api_key = api_key
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


async def llm_chat_stream(
    messages: list[dict[str, str]],
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    *,
    max_tokens: int = 5000,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    OpenAI 兼容接口的真正流式（/chat/completions, stream=true）。
    说明：
    - 该函数不依赖 AgentScope，直接用 httpx 消费 SSE 流。
    - 主要用于“5-Agent 仍在编排，但最终回答 token 级流式输出”的体验优化。
    """
    bu = (base_url or "").strip().rstrip("/")
    if not bu:
        return
    # 兼容：base_url 若未以 /v1 结尾则补齐
    if not bu.endswith("/v1"):
        bu = bu + "/v1"
    url = bu + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    payload = {
        "model": (model or "").strip() or "qwen3-32b",
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        import httpx
        import json as _json
    except Exception:
        return

    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            # 过滤 <think>...</think>：流式 token 可能把标签拆开，需做状态机处理
            in_think = False
            carry = ""

            def _filter_think(delta: str) -> str:
                nonlocal in_think, carry
                if not delta:
                    return ""
                s = carry + delta
                carry = ""
                out_parts: list[str] = []
                i = 0
                while i < len(s):
                    if not in_think:
                        j = s.find("<think>", i)
                        if j == -1:
                            out_parts.append(s[i:])
                            break
                        out_parts.append(s[i:j])
                        in_think = True
                        i = j + len("<think>")
                    else:
                        k = s.find("</think>", i)
                        if k == -1:
                            # 仍在 think 中，丢弃剩余
                            break
                        in_think = False
                        i = k + len("</think>")

                # 处理标签被拆开的情况：保留末尾可能的 "<think" 或 "</think" 前缀
                tail = s[max(0, len(s) - 8) :]
                if not in_think:
                    if "<think" in tail and "<think>" not in tail:
                        # 将未完整标签移到 carry，避免输出破碎标签
                        p = s.rfind("<think")
                        if p != -1 and p >= len(s) - 8:
                            carry = s[p:]
                            # 回退 out_parts 最后追加的那段
                            joined = "".join(out_parts)
                            return joined[: max(0, len(joined) - len(carry))]
                    if "</think" in tail and "</think>" not in tail:
                        p = s.rfind("</think")
                        if p != -1 and p >= len(s) - 8:
                            carry = s[p:]
                            joined = "".join(out_parts)
                            return joined[: max(0, len(joined) - len(carry))]
                return "".join(out_parts)

            async for line in resp.aiter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    break
                try:
                    obj = _json.loads(data_str)
                except Exception:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    filtered = _filter_think(str(content))
                    if filtered:
                        yield filtered
