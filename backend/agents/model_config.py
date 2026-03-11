# -*- coding: utf-8 -*-
"""
AgentScope ChatModel 公共配置：从 model_gateway.config 创建 OpenAIChatModel / DashScopeChatModel。
供 FAQ、RAG、路由、Insight、产品对比/解读/推荐、报告生成等智能体复用，避免各模块重复实现。
"""
from __future__ import annotations

import os
from typing import Any

try:
    from agentscope.model import OpenAIChatModel, DashScopeChatModel
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    OpenAIChatModel = None  # type: ignore[misc, assignment]
    DashScopeChatModel = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False


def create_chat_model_from_config() -> Any:
    """
    从 model_gateway.config 读取 LLM 配置，按 base_url / api_key 创建 AgentScope ChatModel。

    - base_url 不为空：使用 OpenAIChatModel（内网/代理网关）。
    - base_url 为空且 api_key 不为空：使用 DashScopeChatModel（config 中的 LLM_API_KEY）。
    - 否则若环境变量 DASHSCOPE_API_KEY 存在：使用 DashScopeChatModel。
    - 否则返回 None。
    """
    if not _AGENTSCOPE_AVAILABLE or (OpenAIChatModel is None and DashScopeChatModel is None):
        return None
    try:
        from model_gateway.config import load_gateway_config
    except ImportError:
        return None
    cfg = load_gateway_config()
    llm = cfg.llm
    base_url = (llm.base_url or "").strip()
    api_key = (llm.api_key or "").strip()
    generate_kwargs = {
        "temperature": llm.temperature,
        "max_tokens": llm.max_tokens,
    }
    if base_url:
        return OpenAIChatModel(
            model_name=llm.model or "qwen3-32b",
            api_key=api_key or None,
            stream=False,
            client_kwargs={"base_url": base_url},
            generate_kwargs=generate_kwargs,
            enable_thinking=False,
        )
    if api_key:
        return DashScopeChatModel(
            model_name=llm.model or "qwen3-32b",
            api_key=api_key,
            stream=False,
            generate_kwargs=generate_kwargs,
            enable_thinking=False,
        )
    return None
