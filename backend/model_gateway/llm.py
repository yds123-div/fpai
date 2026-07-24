"""
LLM 统一调用：通过 GatewayChatModel（原生 AgentScope ChatModelBase 子类）调用。

T4 #22：``llm_chat`` 改为 ``stream=False`` 的 ``GatewayChatModel`` 薄包装
（7 调用者零改动，对外契约不变）。熔断/httpx 回退/Opik span 预留统一在
``GatewayChatModel._call_api`` 内；本模块仅做同步桥接（解 async 模型 <-> 同步
对外契约）+ 文本抽取。``llm_chat_stream`` 保留 httpx 直连流式（栅栏 #6 形态
由 T8 ShapeAdapter 定）。

异常类从 ``model_gateway.exceptions`` re-export，向后兼容
``from model_gateway.llm import ModelGatewayError`` 等既有 import。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, AsyncGenerator

from model_gateway.config import GatewayConfig, load_gateway_config
from model_gateway.exceptions import ModelGatewayError, ModelNotConfiguredError
from model_gateway.gateway_model import build_gateway_model, _dicts_to_msgs
from pkg.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "ModelGatewayError",
    "ModelNotConfiguredError",
    "llm_chat",
    "llm_chat_stream",
    "build_gateway_model",
]


def _content_from_chat_response(response: Any) -> str:
    """从 AgentScope ChatResponse 中取出首段文本内容。"""
    if response is None:
        return ""
    content = getattr(response, "content", None) or []
    parts = []
    for block in content:
        # 普通文本块
        if hasattr(block, "text"):
            parts.append(block.text or "")
        # 部分 SDK 用 dict 描述 block
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", "") or "")
        # thinking 块：用于展示推理过程（以 <think> 包裹）
        elif hasattr(block, "thinking"):
            th = block.thinking or ""
            if th:
                parts.append(f"<think>{th}</think>")
        elif isinstance(block, dict) and block.get("type") == "thinking":
            th = block.get("thinking") or ""
            if th:
                parts.append(f"<think>{th}</think>")
    return "\n".join(parts).strip()


async def _chat_via_gateway(model: Any, messages: list[dict]) -> str:
    """通过 GatewayChatModel 调用（async 内部，stream=False 单次结果）。

    ``llm_chat`` 对外是同步 + ``list[dict]``；``GatewayChatModel.__call__`` 是
    async + ``list[Msg]``。本函数做 list[dict] -> list[Msg] 转换 + 调用 + 文本抽取。
    """
    msgs = _dicts_to_msgs(messages)
    resp = await model(msgs)
    return _content_from_chat_response(resp)


def _run_gateway_in_new_loop(model: Any, messages: list[dict]) -> str:
    """在独立事件循环中运行 _chat_via_gateway（用于线程内调用，避免与主循环冲突）。"""
    loop = asyncio.new_event_loop()
    try:
        # 确保协程/回调在该 loop 上正确注册
        prev_loop = None
        try:
            prev_loop = asyncio.get_event_loop()
        except Exception:
            prev_loop = None
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_chat_via_gateway(model, messages))
    finally:
        # 某些底层库（如 httpx/anyio）会在退出阶段异步关闭连接池。
        # 若直接 loop.close()，可能触发 "RuntimeError: Event loop is closed"。
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for t in pending:
                    t.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            # 关闭异步生成器，避免挂起的清理任务泄漏
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        finally:
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            loop.close()


def llm_chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    config: GatewayConfig | None = None,
    *,
    enable_thinking: bool = False,
) -> str:
    """调用 LLM 对话接口（同步，对外契约不变）。

    T4 #22：薄包装 stream=False 的 GatewayChatModel。熔断/httpx 回退/Opik span
    预留统一在 ``GatewayChatModel._call_api`` 内；本函数仅做同步桥接。未配置
    （无 base_url 且无 api_key）时抛 ``ModelNotConfiguredError``；熔断打开或
    fallback 耗尽时抛 ``ModelGatewayError``（约束：抛异常不静默）。

    7 个调用者（retrieval / compliance×2 / knowledge / runtime / framework）
    零改动：签名 ``(messages, model, base_url, api_key, config, *,
    enable_thinking) -> str`` 不变。
    """
    cfg = config or load_gateway_config()
    if model:
        cfg.llm.model = model
    if base_url is not None:
        cfg.llm.base_url = base_url
    if api_key is not None:
        cfg.llm.api_key = api_key

    # 工厂在无 base_url 且无 api_key 时抛 ModelNotConfiguredError（对外契约一致）
    gm = build_gateway_model(stream=False, config=cfg, enable_thinking=enable_thinking)

    # 同步桥接 async 模型：检测是否已在事件循环内
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        running_loop = False
    else:
        running_loop = True

    if not running_loop:
        # 无运行 loop：直接 asyncio.run
        content = asyncio.run(_chat_via_gateway(gm, messages))
    else:
        # 已在 loop 内（如 FastAPI 异步请求）：线程内新建 loop 执行，
        # 避免 asyncio.run() 报错。注：ADR-0002 contextvars 约束由此路径引入，
        # Opik span 恢复时需在主线程包裹工作线程（见 gateway_model 注释）。
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            content = pool.submit(
                _run_gateway_in_new_loop, gm, messages
            ).result()
    return content or ""


async def llm_chat_stream(
    messages: list[dict[str, str]],
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    *,
    max_tokens: int = 5000,
    temperature: float = 0.3,
    show_thinking: bool = False,
) -> AsyncGenerator[str, None]:
    """
    OpenAI 兼容接口的真正流式（/chat/completions, stream=true）。
    说明：
    - 该函数不依赖 AgentScope，直接用 httpx 消费 SSE 流。
    - 主要用于“5-Agent 仍在编排，但最终回答 token 级流式输出”的体验优化。
    """
    cfg = load_gateway_config()
    bu = (base_url or "").strip().rstrip("/")
    # base_url 未传入时，回退到网关默认配置（便于在 UI 仅传 model_id 时仍可流式）
    if not bu:
        bu = (cfg.llm.base_url or "").strip().rstrip("/")
    if not bu:
        return
    import re as _re
    # 兼容：base_url 若未以 /v<N> 结尾则补齐 /v1；已有版本路径则不再追加
    if not _re.search(r"/v\d+$", bu):
        bu = bu + "/v1"
    url = bu + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    _api_key = (api_key or "").strip() or (cfg.llm.api_key or "").strip()
    if _api_key:
        headers["Authorization"] = f"Bearer {_api_key}"
    payload = {
        "model": (model or "").strip() or (cfg.llm.model or "").strip() or "qwen3-32b",
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
                    if show_thinking:
                        # 直接返回，前端自行解析 <think>...</think> 并折叠展示
                        yield str(content)
                    else:
                        filtered = _filter_think(str(content))
                        if filtered:
                            yield filtered
