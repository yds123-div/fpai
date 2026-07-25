# -*- coding: utf-8 -*-
"""颗粒化取数工具包（T5/#23）。

4 个只读 ``FunctionTool``（查榜单 / 查详情 / 名称转代码 / kb）+ ALLOW 权限规则。
详见 ``fund_tools`` 模块说明。
"""
from __future__ import annotations

from .fund_tools import (
    FUND_TOOL_FUNCS,
    FUND_TOOL_NAMES,
    build_fund_function_tools,
    build_fund_permission_context,
    build_fund_permission_rules,
    build_fund_toolkit,
    query_fund_detail,
    query_fund_rank,
    query_knowledge_base,
    resolve_fund_code,
)

__all__ = [
    "FUND_TOOL_FUNCS",
    "FUND_TOOL_NAMES",
    "build_fund_function_tools",
    "build_fund_permission_context",
    "build_fund_permission_rules",
    "build_fund_toolkit",
    "query_fund_detail",
    "query_fund_rank",
    "query_knowledge_base",
    "resolve_fund_code",
]
