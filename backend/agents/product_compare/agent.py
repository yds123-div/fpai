# -*- coding: utf-8 -*-
"""
产品对比智能体：Data Access + 产品要素抽取 + ReAgent 差异总结；多产品多维对比表。

T020：向 AgentScope 注册为工具 product_compare_query；多产品多维对比表、差异总结。
"""
from __future__ import annotations

import asyncio
from typing import Any

from data_access import get_data
from agents.product_element.extract import extract_elements
from agents.product_element.types import ProductElements

try:
    from agentscope.tool import ToolResponse, Toolkit
    from agentscope.message import TextBlock
    from agentscope.agent import ReActAgent
    from agentscope.formatter import DashScopeChatFormatter
    from agentscope.memory import InMemoryMemory
    from agentscope.message import Msg
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    ToolResponse = None  # type: ignore[misc, assignment]
    Toolkit = None  # type: ignore[misc, assignment]
    TextBlock = None  # type: ignore[misc, assignment]
    ReActAgent = None  # type: ignore[misc, assignment]
    DashScopeChatFormatter = None  # type: ignore[misc, assignment]
    InMemoryMemory = None  # type: ignore[misc, assignment]
    Msg = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False

PRODUCT_DETAIL_MODEL = "product_detail"
PRODUCT_LIST_MODEL = "products"

# 对比维度（与 ProductElements 字段对应，用于生成对比表）
COMPARE_DIMENSIONS = [
    ("term", "期限"),
    ("fee_rate", "费率"),
    ("risk_level", "风险等级"),
    ("redemption_rules", "赎回规则"),
    ("investment_direction", "投向"),
    ("performance_benchmark", "业绩基准"),
    ("income_rules", "收益规则"),
]


def _get_product_by_id(
    product_id: str,
    permission_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """通过 data_access 按 product_id 获取单条产品记录。"""
    product_id = (product_id or "").strip()
    if not product_id:
        return None
    try:
        records, _ = get_data(
            model_code=PRODUCT_DETAIL_MODEL,
            request_params={"product_id": product_id},
            permission_context=permission_context,
        )
        if records:
            return records[0]
    except Exception:
        pass
    try:
        records, _ = get_data(
            model_code=PRODUCT_LIST_MODEL,
            request_params={"product_id": product_id, "page": 1, "page_size": 1},
            permission_context=permission_context,
        )
        if records:
            return records[0]
    except Exception:
        pass
    return None


def _text_from_product(product: dict[str, Any]) -> str:
    """从产品记录中拼接可用于要素抽取的文本。"""
    parts = []
    for key in ("description", "terms", "prospectus", "product_name", "name", "summary", "risk_disclosure"):
        v = product.get(key)
        if v and isinstance(v, str) and v.strip():
            parts.append(v.strip())
    if not parts:
        parts = [str(v) for v in product.values() if isinstance(v, str) and v.strip()]
    return "\n\n".join(parts)[:12000]


def _build_comparison_table(
    products: list[dict[str, Any]],
    elements_list: list[ProductElements],
) -> list[dict[str, Any]]:
    """
    构建多维对比表。每行一个维度，含各产品在该维度的值。
    返回 [ {"dimension": "期限", "product_0": "1年", "product_1": "2年", ...}, ... ]
    """
    if not products or not elements_list or len(products) != len(elements_list):
        return []
    rows = []
    for key, label in COMPARE_DIMENSIONS:
        row: dict[str, Any] = {"dimension": label}
        for i, elem in enumerate(elements_list):
            d = elem.to_dict()
            v = d.get(key)
            row[f"product_{i}"] = (str(v).strip() if v is not None else "") or "—"
        rows.append(row)
    return rows


from agents.model_config import create_chat_model_from_config


async def _summary_via_reagent(
    comparison_table: list[dict[str, Any]],
    product_names: list[str],
) -> str | None:
    """用 ReActAgent 根据对比表生成差异总结。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return None
    model = create_chat_model_from_config()
    if model is None:
        return None
    # 表格文本：每行 维度 | 产品A | 产品B | ...
    header = "维度 | " + " | ".join(product_names[:5])
    lines = [header]
    for row in comparison_table:
        dim = row.get("dimension", "")
        cells = [str(row.get(f"product_{i}", "—")) for i in range(len(product_names))]
        lines.append(f"{dim} | " + " | ".join(cells))
    table_text = "\n".join(lines)
    sys_prompt = """你是金融产品对比助手。根据给定的多产品多维对比表，用 2～4 段话写出差异总结：
1) 期限与流动性差异；2) 费率与收益特征差异；3) 风险与适用客群差异；4) 其他关键差异或选购建议。
语言简洁、客观，不编造表中未出现的信息。"""
    user_content = f"对比表：\n{table_text}\n\n请输出差异总结。"
    agent = ReActAgent(
        name="ProductCompareAgent",
        sys_prompt=sys_prompt,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=Toolkit(),
    )
    msg_res = await agent(Msg("user", user_content, "user"))
    if msg_res is None:
        return None
    text = msg_res.get_text_content() if hasattr(msg_res, "get_text_content") else None
    if not text and hasattr(msg_res, "get_content_blocks"):
        blocks = msg_res.get_content_blocks("text")
        if blocks:
            text = "\n".join(getattr(b, "text", b.get("text", "")) for b in blocks)
    return (text or "").strip() or None


def query_product_compare(
    product_ids: list[str],
    permission_context: dict[str, Any] | None = None,
    use_reagent: bool = True,
) -> dict[str, Any]:
    """
    多产品多维对比：Data Access 取产品 → 要素抽取 → 对比表 → ReAgent 差异总结。

    Args:
        product_ids: 至少 2 个产品 ID。
        permission_context: 权限上下文。
        use_reagent: 是否用 ReAgent 生成差异总结。

    Returns:
        products: 产品基础信息列表
        comparison_table: 多维对比表（每行一个维度）
        summary: 差异总结文案
        answer: 完整展示用文本（表 + 总结）
    """
    ids = [str(pid).strip() for pid in (product_ids or []) if str(pid).strip()]
    if len(ids) < 2:
        return {
            "products": [],
            "comparison_table": [],
            "summary": "",
            "answer": "请至少提供 2 个产品 ID 进行对比。",
        }
    products: list[dict[str, Any]] = []
    elements_list: list[ProductElements] = []
    for pid in ids:
        product = _get_product_by_id(pid, permission_context)
        if not product:
            return {
                "products": [],
                "comparison_table": [],
                "summary": "",
                "answer": f"未找到产品（id: {pid}）或无权访问，请检查后重试。",
            }
        products.append(product)
        text = _text_from_product(product)
        elements_list.append(extract_elements(text, use_llm=True))

    comparison_table = _build_comparison_table(products, elements_list)
    product_names = [
        p.get("name") or p.get("product_name") or p.get("id") or f"产品{i}"
        for i, p in enumerate(products)
    ]
    summary = ""
    if use_reagent:
        try:
            summary = (asyncio.run(_summary_via_reagent(comparison_table, product_names))) or ""
        except Exception:
            pass
    if not summary:
        summary = "请结合上表维度自行查看差异；投资决策请以产品说明书为准。"
    # 纯文本表 + 总结
    table_lines = ["| 维度 | " + " | ".join(product_names) + " |"]
    for row in comparison_table:
        cells = [str(row.get(f"product_{i}", "—")) for i in range(len(products))]
        table_lines.append("| " + row.get("dimension", "") + " | " + " | ".join(cells) + " |")
    answer = "【对比表】\n" + "\n".join(table_lines) + "\n\n【差异总结】\n" + summary
    return {
        "products": [{"id": p.get("id") or p.get("product_id"), "name": p.get("name") or p.get("product_name")} for p in products],
        "comparison_table": comparison_table,
        "summary": summary,
        "answer": answer,
    }


async def product_compare_query(product_ids: str) -> Any:
    """
    产品对比，包装为 ToolResponse。供 toolkit.register_tool_function(product_compare_query) 注册。

    Args:
        product_ids: 逗号分隔的产品 ID，至少 2 个。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    ids = [x.strip() for x in (product_ids or "").split(",") if x.strip()]
    result = query_product_compare(ids)
    text = result.get("answer") or "无法生成对比结果。"
    return ToolResponse(content=[TextBlock(type="text", text=text)])
