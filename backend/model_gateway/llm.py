"""
LLM 统一调用：通过 GatewayChatModel（原生 AgentScope ChatModelBase 子类）调用。

T4 #22：``llm_chat`` 改为 ``stream=False`` 的 ``GatewayChatModel`` 薄包装
（7 调用者零改动，对外契约不变）。熔断/httpx 回退/Opik span 预留统一在
``GatewayChatModel._call_api`` 内；本模块仅做同步桥接（解 async 模型 <-> 同步
对外契约）+ 文本抽取。流式由 T8 ``ShapeAdapter`` 承担（栅栏 #6 保形），T10 删除
``llm_chat_stream`` 后本模块仅保留同步 ``llm_chat``。

异常类从 ``model_gateway.exceptions`` re-export，向后兼容
``from model_gateway.llm import ModelGatewayError`` 等既有 import。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from model_gateway.config import GatewayConfig, load_gateway_config
from model_gateway.exceptions import ModelGatewayError, ModelNotConfiguredError
from model_gateway.gateway_model import build_gateway_model, _dicts_to_msgs
from pkg.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "ModelGatewayError",
    "ModelNotConfiguredError",
    "llm_chat",
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
