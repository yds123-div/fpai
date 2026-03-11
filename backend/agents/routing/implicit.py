# -*- coding: utf-8 -*-
"""
隐式智能体路由：将下游智能体包装成工具函数，由路由智能体根据用户查询决定调用哪个工具。

参考 workflow_routing 隐式 Routing：工具函数内可实例化子 ReActAgent，执行后返回 ToolResponse。
LLM 从 model_gateway.config 读取；根据 api_key 是否有值选用 OpenAIChatModel（网关）或 DashScopeChatModel。
"""
from __future__ import annotations

import os
from typing import Any

try:
    from agentscope.tool import Toolkit, ToolResponse
    from agentscope.message import TextBlock
    from agentscope.agent import ReActAgent
    from agentscope.formatter import DashScopeChatFormatter
    from agentscope.memory import InMemoryMemory
    from agentscope.message import Msg
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    Toolkit = None  # type: ignore[misc, assignment]
    ToolResponse = None  # type: ignore[misc, assignment]
    TextBlock = None  # type: ignore[misc, assignment]
    ReActAgent = None  # type: ignore[misc, assignment]
    DashScopeChatFormatter = None  # type: ignore[misc, assignment]
    InMemoryMemory = None  # type: ignore[misc, assignment]
    Msg = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False


# ----- 已接入：FAQ -----


def _get_faq_tool():
    """延迟导入，避免循环依赖。"""
    from agents.faq import faq_query
    return faq_query


# ----- 已接入：RAG -----


def _get_rag_tool():
    """延迟导入，避免循环依赖。"""
    from agents.rag import rag_query
    return rag_query


# ----- 占位工具（后期对接 insight / product_compare / report_generate / product_list）-----


def _get_insight_tool():
    """延迟导入，避免循环依赖。"""
    from agents.insight import insight_query
    return insight_query


def _get_product_compare_tool():
    """延迟导入，避免循环依赖。"""
    from agents.product_compare import product_compare_query
    return product_compare_query

async def _product_element_query(product_id: str) -> Any:
    """产品要素查询：根据产品 ID 查询产品要素。后期对接 agents.product_element_query。

    Args:
        product_id: 产品 ID。
    """
    if ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装")
    return ToolResponse(content=[TextBlock(type="text", text="[产品要素查询] 功能开发中，敬请期待。")])


def _get_product_element_query():
    """延迟导入，与注册表一致。"""
    return _product_element_query

# ----- 已接入：产品解读 -----


def _get_product_interpret_tool():
    """延迟导入，避免循环依赖。"""
    from agents.product_interpret import product_interpret_query
    return product_interpret_query

def _get_product_recommend_tool():
    """延迟导入，避免循环依赖。"""
    from agents.product_recommend import product_recommend_query
    return product_recommend_query

def _get_report_generate_tool():
    """延迟导入，避免循环依赖。"""
    from agents.report_generate import report_generate_query
    return report_generate_query

# ----- 已接入：产品列表 -----


def _get_product_list_tool():
    """延迟导入，避免循环依赖。"""
    from agents.product_list import product_list_query
    return product_list_query


# ----- 根据 config 创建 AgentScope ChatModel -----

from agents.model_config import create_chat_model_from_config


# ----- 路由 Toolkit 与 路由智能体（T024 从 registry 构建）-----


def build_routing_toolkit() -> Any:
    """
    从智能体注册表（agents.registry）构建 Toolkit，注册 FAQ/RAG/Insight/产品对比/产品要素查询/产品解读/产品列表/产品推荐/报告生成 等工具；支持配置化扩展。
    """
    if not _AGENTSCOPE_AVAILABLE or Toolkit is None:
        return None
    from agents.registry import build_toolkit_from_registry
    return build_toolkit_from_registry()


def get_implicit_router():
    """
    创建并返回隐式路由智能体（ReActAgent），其 toolkit 包含 FAQ / RAG / Insight / 产品对比 / 产品要素查询 / 产品解读 / 产品推荐 / 报告生成 / 产品列表 等工具。
    模型由 model_gateway.config 与 api_key 判定：有网关 api_key+base_url 用 OpenAIChatModel，否则用 DashScopeChatModel；均未配置时返回 None。
    """
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None:
        return None
    model = create_chat_model_from_config()
    if model is None:
        return None
    toolkit = build_routing_toolkit()
    if toolkit is None:
        return None
    return ReActAgent(
        name="Router",
        sys_prompt=(
            "你是一个路由智能体。根据用户查询调用合适工具完成任务（FAQ 问答、RAG 检索、产品对比、产品解读、产品推荐、报告生成、产品列表等）。"
            "重要：若某工具已返回「未找到匹配的 FAQ」或「未检索到相关片段」，不要重复调用同一工具；应基于该结果直接给用户一个简洁回复（如说明暂未找到相关资料，或根据常识简要回答），勿多次重试同一工具。"
        ),
        model=model,
        formatter=DashScopeChatFormatter(),
        toolkit=toolkit,
        memory=InMemoryMemory(),
    )

