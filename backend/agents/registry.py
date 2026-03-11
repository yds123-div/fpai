# -*- coding: utf-8 -*-
"""
智能体注册表：各能力向 AgentScope 注册为 Toolkit 工具；id、名称、意图映射、入口函数、超时/成本约束；支持配置化扩展。

T024：见 technical_design §3.2；供 routing/implicit 等从注册表构建 Toolkit，编排/审计可查询能力清单。
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable

# 入口加载器：字符串为 "module:attr" 延迟导入并返回可调用对象（如 faq_query）；也可直接传 callable
EntryLoader = str | Callable[[], Any]

@dataclass
class ToolEntry:
    """单条工具注册项。"""
    id: str
    name: str
    intent_keywords: list[str] = field(default_factory=list)
    entry_loader: EntryLoader = ""
    timeout_seconds: int | None = None
    cost_constraint: str | None = None

    def resolve_entry(self) -> Any:
        """解析 entry_loader 得到实际可注册的入口（异步工具函数）。"""
        if callable(self.entry_loader):
            fn = self.entry_loader
            return fn() if callable(fn) else fn
        if not isinstance(self.entry_loader, str) or ":" not in self.entry_loader:
            return None
        mod_path, attr = self.entry_loader.rsplit(":", 1)
        try:
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, attr, None)
            return fn() if callable(fn) else fn
        except (ImportError, AttributeError):
            return None


# 内置工具注册表：与 routing/implicit 中已接入工具一一对应；entry_loader 指向 implicit 中的 _get_xxx_tool
BUILTIN_ENTRIES: list[ToolEntry] = [
    ToolEntry(
        id="faq",
        name="FAQ 问答",
        intent_keywords=["FAQ", "常见问题", "问答", "话术"],
        entry_loader="agents.routing.implicit:_get_faq_tool",
        timeout_seconds=30,
    ),
    ToolEntry(
        id="rag",
        name="RAG 检索回答",
        intent_keywords=["RAG", "检索", "知识库", "文档", "研报", "政策"],
        entry_loader="agents.routing.implicit:_get_rag_tool",
        timeout_seconds=45,
    ),
    ToolEntry(
        id="insight",
        name="猜你想问/洞察",
        intent_keywords=["猜你想问", "洞察", "推荐问题", "suggestedQuestions"],
        entry_loader="agents.routing.implicit:_get_insight_tool",
        timeout_seconds=15,
    ),
    ToolEntry(
        id="product_compare",
        name="产品对比",
        intent_keywords=["产品对比", "对比", "多产品", "比较"],
        entry_loader="agents.routing.implicit:_get_product_compare_tool",
        timeout_seconds=60,
    ),
    ToolEntry(
        id="product_element_query",
        name="产品要素查询",
        intent_keywords=["产品要素", "条款", "要素查询"],
        entry_loader="agents.routing.implicit:_get_product_element_query",
        timeout_seconds=20,
    ),
    ToolEntry(
        id="product_interpret",
        name="产品解读",
        intent_keywords=["产品解读", "解读", "要点", "风险提示"],
        entry_loader="agents.routing.implicit:_get_product_interpret_tool",
        timeout_seconds=45,
    ),
    ToolEntry(
        id="product_list",
        name="产品列表查询",
        intent_keywords=["产品列表", "可售产品", "产品筛选", "列表"],
        entry_loader="agents.routing.implicit:_get_product_list_tool",
        timeout_seconds=20,
    ),
    ToolEntry(
        id="product_recommend",
        name="产品推荐",
        intent_keywords=["产品推荐", "推荐", "客户画像", "匹配"],
        entry_loader="agents.routing.implicit:_get_product_recommend_tool",
        timeout_seconds=45,
    ),
    ToolEntry(
        id="report_generate",
        name="报告生成",
        intent_keywords=["报告", "周报", "月报", "市场解读", "解读稿"],
        entry_loader="agents.routing.implicit:_get_report_generate_tool",
        timeout_seconds=90,
    ),
]


def _load_entries_from_config() -> list[ToolEntry]:
    """从 config（T014）读取扩展注册项；config_key=agent_registry，结构为 list of {id, name, intent_keywords, entry_loader, timeout_seconds?}。"""
    try:
        from config import get_config
    except ImportError:
        return []
    data = get_config("agent_registry", use_cache=True)
    if not data or not isinstance(data, dict):
        return []
    items = data.get("tools") or data.get("entries")
    if not isinstance(items, list):
        return []
    out: list[ToolEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        eid = item.get("id") or item.get("tool_id")
        name = item.get("name") or item.get("tool_name") or str(eid)
        keywords = item.get("intent_keywords") or item.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        loader = item.get("entry_loader") or item.get("entry")
        if not eid or not loader:
            continue
        out.append(ToolEntry(
            id=str(eid),
            name=str(name),
            intent_keywords=[str(k) for k in keywords],
            entry_loader=str(loader),
            timeout_seconds=item.get("timeout_seconds"),
            cost_constraint=item.get("cost_constraint"),
        ))
    return out


def get_all_entries() -> list[ToolEntry]:
    """返回全部注册项：内置 + 配置扩展。"""
    return list(BUILTIN_ENTRIES) + _load_entries_from_config()


def get_entries_by_intent(intent: str) -> list[ToolEntry]:
    """按意图关键词过滤注册项（用于缩小候选工具集）。"""
    intent_lower = (intent or "").strip().lower()
    if not intent_lower:
        return get_all_entries()
    return [e for e in get_all_entries() if any(intent_lower in (k or "").lower() for k in e.intent_keywords)]


def build_toolkit_from_registry(
    entries: list[ToolEntry] | None = None,
    toolkit_class: Any = None,
) -> Any:
    """
    根据注册表构建 AgentScope Toolkit，逐条注册入口函数。

    Args:
        entries: 若为 None 则使用 get_all_entries()。
        toolkit_class: 若提供则用该类构造（默认从 agentscope.tool 取 Toolkit）。

    Returns:
        Toolkit 实例；若 AgentScope 不可用或无条目则返回 None。
    """
    if toolkit_class is None:
        try:
            from agentscope.tool import Toolkit
            toolkit_class = Toolkit
        except ImportError:
            return None
    if entries is None:
        entries = get_all_entries()
    if not entries:
        return None
    toolkit = toolkit_class()
    for entry in entries:
        try:
            fn = entry.resolve_entry()
            if fn is not None:
                toolkit.register_tool_function(fn)
        except Exception:
            continue
    return toolkit
