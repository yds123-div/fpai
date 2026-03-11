# -*- coding: utf-8 -*-
"""
产品解读智能体：Data Access + 产品要素抽取 + 可选 Retrieval + LLM；输出结构化要点与风险提示；向 AgentScope 注册为工具。
"""
from agents.product_interpret.agent import query_product_interpret, product_interpret_query

__all__ = ["query_product_interpret", "product_interpret_query"]
