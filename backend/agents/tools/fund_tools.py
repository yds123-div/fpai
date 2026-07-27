# -*- coding: utf-8 -*-
"""T5（#23）：颗粒化取数 FunctionTool + 名称转代码可信集权威 + ALLOW 权限规则。

栅栏 #1（基金代码可信集）原生重表达：
- 4 个只读取数工具（查榜单 / 查详情 / 名称转代码 / kb）包成 AgentScope ``FunctionTool``，
  ``input_schema`` 由函数签名 + docstring 自动抽取（``tool/_utils._extract_input_schema``）；
  工具只取数、不调 LLM。
- 名称转代码工具 = 可信集权威：6 位 raw code 经 ``fund_code_registry.is_trusted`` 校验，
  臆测代码 ``raise AgentOrientedException`` 中止回灌自愈（栅栏 #2 M4：``toolkit.call_tool``
  捕获后转 ``ToolResponse(state=ERROR)`` 回灌模型）；名称经 ``resolve`` 多策略匹配，未命中亦中止。
  ``code_provided`` 分支不再直接采纳臆测代码（修"直接采纳臆测代码"缺口）。

  注（ADR 关系，``docs/agents/domain.md`` 要求显式标注）：本处的 abort 回灌是 spec #18 栅栏 #2 M4
  对 ADR-0001 plan-JSON 重试机制的**原生重表达**——plan-JSON 机制弃用，其安全意图以 SI-1~12
  存活、由 M1-M5 重写。非与 ADR-0001 决策 4 矛盾，而是 spec 显式取代（旧 plan 路径手写重试环
  在切换 PR 删除，见 spec #18「切换策略与旧代码命运」）。
- 4 只读工具注册 ``PermissionRule(ALLOW)``（R1 查明 ``FunctionTool.check_permissions`` 默认
  ``ASK``，不注册则每次调用暂停等确认）。M3 危险集暂空、休眠待命（将来写操作接入 ASK 时不改架构）。

agent 装配（见后续工单）：
    state = AgentState(permission_context=build_fund_permission_context())
    agent = Agent(..., toolkit=build_fund_toolkit(), state=state, react_config=ReActConfig(max_iters=8))

测试路径说明：``backend/pyproject.toml`` 配置 testpaths=["../tests"]、pythonpath=["."]，
运行：``cd backend && python -m pytest ../tests/test_fund_tools.py -c pyproject.toml -v``
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from agentscope.exception import AgentOrientedException
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionRule,
)
from agentscope.tool import FunctionTool, Toolkit, ToolBase


# kb 工具返回的每条 chunk_text 预览截断长度（避免单条过长撑爆模型上下文）
_KB_CHUNK_TEXT_PREVIEW = 500


# ---------------------------------------------------------------------------
# 4 个只读取数工具（只取数、不调 LLM）
# ---------------------------------------------------------------------------
async def query_fund_rank(question: str) -> str:
    """查询基金榜单/排行数据。

    按用户指定的时间区间（近1月/近1年/今天等）与风险偏好，返回收益排序的 TopN 基金列表，
    含基金代码、名称、收益、稳健性参考。仅取数，不调用 LLM。

    Args:
        question: 用户的榜单查询问题，例如 "近一月涨幅前5的基金" 或 "今天涨幅榜"。
    """
    from agents.skills.product_query.runtime import run as _run_rank

    return await _run_rank((question or "").strip(), {})


async def query_fund_detail(question: str) -> str:
    """查询基金详情数据（单只或多只）。

    从问题中提取 6 位基金代码，聚合基本信息、业绩表现、资产配置、风险等数据。
    仅取数，不调用 LLM。

    Args:
        question: 用户的详情查询问题，需含 6 位基金代码，例如 "161039 和 110011 的对比"。
    """
    from agents.skills.product_compare.runtime import run as _run_detail

    return await _run_detail((question or "").strip(), {})


async def resolve_fund_code(query: str) -> str:
    """把基金名称解析为可信基金代码，或校验用户给出的代码是否在可信集内。

    栅栏 #1 权威：6 位代码经 ``fund_code_registry.is_trusted`` 校验，臆测代码被拒
    （``raise AgentOrientedException`` 中止回灌自愈）；名称经 ``resolve`` 多策略匹配，
    未命中亦中止。仅查可信集，不调用 LLM。

    Args:
        query: 基金名称或 6 位基金代码，例如 "易方达蓝筹精选" 或 "005827"。
    """
    from agents.skills.fund_code_registry import is_trusted, resolve

    raw = (query or "").strip()
    if not raw:
        raise AgentOrientedException(
            "名称转代码工具收到空输入；请提供基金名称或 6 位基金代码。",
        )

    # code_provided 分支：校验 raw code（修"直接采纳臆测代码"缺口）
    codes = re.findall(r"(?<!\d)\d{6}(?!\d)", raw)
    if codes:
        trusted_codes = [c for c in codes if is_trusted(c)]
        rejected = [c for c in codes if not is_trusted(c)]
        if rejected:
            # 臆测代码 -> 中止回灌自愈（栅栏 #2 M4）
            raise AgentOrientedException(
                f"基金代码 {'/'.join(rejected)} 不在可信集内（akshare 基金列表），"
                "可能是臆测代码；请改用基金名称重新查询，或确认代码后重试。",
            )
        # 全部可信：取可信记录（resolve 命中 registry 缓存，不触网）。
        # 复用 T3 的 ResolveHit dataclass -> asdict，避免手搓 dict 退回 Primitive Obsession。
        records: list[dict[str, Any]] = []
        for code in trusted_codes:
            r = resolve(code)
            if not r.matched or not r.hits:
                # is_trusted 已通过却 resolve 未命中：可信集在两次调用间不一致（理论不可能，
                # 缓存共享）。以中止回灌自愈暴露该不一致，而非静默返回空记录。
                raise AgentOrientedException(
                    f"代码 {code} 通过可信校验但解析失败，请重试。",
                )
            records.append(asdict(r.hits[0]))
        return json.dumps(
            {"ok": True, "mode": "code_provided", "codes": records},
            ensure_ascii=False,
        )

    # 名称分支：registry.resolve 多策略匹配（精确/包含/去份额后缀/相似度）
    r = resolve(raw)
    if not r.matched:
        # 查不到 -> 中止回灌自愈
        raise AgentOrientedException(
            f"未在可信集内找到与 '{raw}' 匹配的基金；请确认名称或改用 6 位基金代码。",
        )
    matches = [asdict(h) for h in r.hits]
    return json.dumps(
        {"ok": True, "mode": "name_to_code", "matches": matches},
        ensure_ascii=False,
    )


async def query_knowledge_base(question: str, top_k: int = 10) -> str:
    """检索理财知识库，返回相关片段与引用。

    仅做检索取数（embedding -> Milvus 召回 -> rerank），不调用 LLM 生成回答；
    回答由上层 agent 据片段组织。

    Args:
        question: 用户的理财知识问题，例如 "基金定投怎么开户"。
        top_k: 返回的最多片段数，默认 10。
    """
    from retrieval.service import retrieve

    q = (question or "").strip()
    if not q:
        return json.dumps(
            {"ok": False, "reason": "empty_question", "chunks": []},
            ensure_ascii=False,
        )
    ret = retrieve(query=q, top_k=top_k)
    chunks = [
        {
            "doc_id": c.doc_id,
            "source": c.source,
            "chunk_text": (c.chunk_text or "")[:_KB_CHUNK_TEXT_PREVIEW],
            "score": c.score,
        }
        for c in ret.citations
    ]
    return json.dumps(
        {"ok": True, "count": len(chunks), "chunks": chunks},
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# FunctionTool 装配 + Toolkit（"basic" 组 = 始终激活的工具白名单）
# ---------------------------------------------------------------------------
# 取数函数注册表。tool_name（= 函数名）须与 PermissionRule.tool_name 一致，
# 供 PermissionEngine 按 tool_name 匹配 ALLOW 规则。
FUND_TOOL_FUNCS = [
    query_fund_rank,
    query_fund_detail,
    resolve_fund_code,
    query_knowledge_base,
]

FUND_TOOL_NAMES = [f.__name__ for f in FUND_TOOL_FUNCS]


def build_fund_function_tools() -> list[ToolBase]:
    """把 4 个取数函数包成只读 ``FunctionTool``。

    ``input_schema`` 由 ``_extract_input_schema`` 从签名 + docstring 自动抽取；
    ``is_read_only=True`` 标注语义（EXPLORE/ACCEPT_EDITS 模式下据此放行）；
    DEFAULT 模式下仍需 ``PermissionRule(ALLOW)``（见 ``build_fund_permission_context``）。
    返回 ``list[ToolBase]`` 以匹配 ``Toolkit(tools=...)`` 的协变需求（list 不变）。
    """
    tools: list[ToolBase] = [
        FunctionTool(f, is_read_only=True) for f in FUND_TOOL_FUNCS
    ]
    return tools


def build_fund_toolkit() -> Toolkit:
    """组装基金取数 ``Toolkit``。

    4 个只读工具放入 "basic" 组（始终激活，agent 无需额外激活即可调用）。
    工具分组即白名单：``Toolkit`` 注册表是工具白名单的单一权威。
    """
    return Toolkit(tools=build_fund_function_tools())


# ---------------------------------------------------------------------------
# 栅栏 #2 M3：4 只读工具注册 PermissionRule(ALLOW)
# ---------------------------------------------------------------------------
# R1 查明 FunctionTool.check_permissions 默认返回 ASK（tool/_adapters.py），
# 不注册 ALLOW 则每次调用都暂停等确认。本模块返回 4 条 ALLOW 规则（rule_content=None
# 表示对该工具的所有输入放行，见 permission/_engine._rule_matches），供
# AgentState.permission_context 装载。
_PERMISSION_RULE_SOURCE = "fund_tools:read_only"


def build_fund_permission_rules() -> list[PermissionRule]:
    """4 个只读工具的 ``ALLOW`` 权限规则。"""
    return [
        PermissionRule(
            tool_name=name,
            rule_content=None,  # None = 匹配该工具的所有输入
            behavior=PermissionBehavior.ALLOW,
            source=_PERMISSION_RULE_SOURCE,
        )
        for name in FUND_TOOL_NAMES
    ]


def build_fund_permission_context() -> PermissionContext:
    """装载 4 条 ALLOW 规则的 ``PermissionContext``。

    用法（agent 装配，见后续工单）::

        state = AgentState(permission_context=build_fund_permission_context())
        agent = Agent(..., state=state)

    Agent 内置 ``PermissionEngine(state.permission_context)`` 会据此放行 4 只读工具
    （DEFAULT 模式：deny -> ask -> tool.check_permissions(ASK 落空) -> allow rules -> ALLOW）。
    """
    allow_rules: dict[str, list[PermissionRule]] = {}
    for rule in build_fund_permission_rules():
        allow_rules.setdefault(rule.tool_name, []).append(rule)
    return PermissionContext(allow_rules=allow_rules)
