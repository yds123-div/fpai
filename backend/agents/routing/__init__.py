# -*- coding: utf-8 -*-
"""
智能体路由：隐式 Routing 初始化。

将下游智能体（FAQ、RAG、Insight、产品对比、报告生成、产品列表等）包装成工具，
由路由智能体根据用户查询决定调用哪个工具。FAQ 已接入，其余为占位，后期与对应智能体注册。
"""
from agents.routing.implicit import (
    build_routing_toolkit,
    get_implicit_router,
)

__all__ = [
    "build_routing_toolkit",
    "get_implicit_router",
]
