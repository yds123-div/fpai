# -*- coding: utf-8 -*-
"""
产品列表查询智能体：调用 data_access 统一接口返回可售产品列表（筛选、分页）；向 AgentScope 注册为工具。
"""
from agents.product_list.agent import query_product_list, product_list_query

__all__ = ["query_product_list", "product_list_query"]
