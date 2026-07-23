# -*- coding: utf-8 -*-
"""E3 原型工具：确定性基金查询 + 只读 FunctionTool 子类。

栅栏 #1（基金代码可信集）的确定性意图在这里以 *最薄* 形态落地：
name -> code 查证 -> 可信集 -> 返回数据。无 akshare 依赖，便于离线跑通。
生产形态见 G4（#7）。
"""
from __future__ import annotations

from typing import Any

from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool

# 可信集（mock）：名称片段 -> 代码。查不到则 abort（栅栏 #1）。
_TRUSTED_FUNDS: dict[str, dict[str, Any]] = {
    "005827": {
        "code": "005827",
        "name": "易方达蓝筹精选混合",
        "type": "混合型",
        "scale": "412.6亿",
        "manager": "张坤",
        "return_y1": "-8.3%",
        "return_3y": "-12.5%",
    },
    "161725": {
        "code": "161725",
        "name": "招商中证白酒指数",
        "type": "指数型",
        "scale": "268.1亿",
        "manager": "侯昊",
        "return_y1": "5.2%",
        "return_3y": "18.7%",
    },
    "110011": {
        "code": "110011",
        "name": "易方达优质精选混合",
        "type": "混合型",
        "scale": "156.3亿",
        "manager": "张坤",
        "return_y1": "-6.1%",
        "return_3y": "-9.4%",
    },
}


class ReadOnlyFunctionTool(FunctionTool):
    """只读 FunctionTool：check_permissions 直接 ALLOW。

    AgentScope 2.0 的 FunctionTool.check_permissions 默认返回 ASK
   （_adapters.py:90），会让 agent 在每次工具调用处暂停等确认。
    只读业务工具在此直接放行；生产应改用 PermissionRule + DB 驱动配置
    （R1 缺口 §5.3）。危险/写操作工具不要继承本类。
    """

    async def check_permissions(self, *_args: Any, **_kwargs: Any) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="read-only prototype tool",
        )


def query_fund(fund_code: str) -> str:
    """查询基金产品信息（确定性，命中可信集即返回，否则中止）。

    Args:
        fund_code: 6 位基金代码，例如 005827。

    Returns:
        基金信息的 JSON 字符串；查不到时返回明确的 not_found。
    """
    import json

    code = (fund_code or "").strip()
    if not code or len(code) != 6 or not code.isdigit():
        return json.dumps({"ok": False, "reason": "invalid_code"}, ensure_ascii=False)
    hit = _TRUSTED_FUNDS.get(code)
    if hit is None:
        # 栅栏 #1：查不到 abort（这里返回 not_found，由模型据实告知用户）
        return json.dumps({"ok": False, "reason": "not_in_trusted_set", "code": code}, ensure_ascii=False)
    return json.dumps({"ok": True, **hit}, ensure_ascii=False)


def lookup_fund_by_name(keyword: str) -> str:
    """按名称关键词模糊匹配可信集内的基金代码。

    Args:
        keyword: 基金名称关键词，例如 "蓝筹" 或 "白酒"。

    Returns:
        匹配到的基金列表 JSON 字符串。
    """
    import json

    kw = (keyword or "").strip()
    matches = [v for v in _TRUSTED_FUNDS.values() if kw in v["name"]]
    return json.dumps({"ok": True, "count": len(matches), "items": matches}, ensure_ascii=False)


def build_fund_toolkit():
    """组装基金查询 Toolkit（工具分组即白名单）。"""
    from agentscope.tool import Toolkit, ToolGroup

    return Toolkit(
        tool_groups=[
            ToolGroup(
                name="fund_query",
                description="基金产品查询工具组：按代码或名称查询可信集内的基金信息。",
                tools=[
                    ReadOnlyFunctionTool(query_fund),
                    ReadOnlyFunctionTool(lookup_fund_by_name),
                ],
            ),
        ],
    )
