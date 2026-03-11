# -*- coding: utf-8 -*-
"""
RAG 智能体：调用 retrieval 检索+生成，输出 answer_blocks 与 citations；向 AgentScope 注册为工具。
"""
from agents.rag.agent import query_rag, rag_query

__all__ = ["query_rag", "rag_query"]
