# -*- coding: utf-8 -*-
"""
产品解读智能体：Data Access + 产品要素抽取 + 可选 Retrieval + AgentScope ReActAgent；输出结构化要点与风险提示。

T019：通过 ReAgent 模式调用大模型；向 AgentScope 注册为工具 product_interpret_query。
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

# 产品详情模型编码（可与 product_list 共用 products 且按 id 筛选，或单独 product_detail）
PRODUCT_DETAIL_MODEL = "product_detail"
PRODUCT_LIST_MODEL = "products"


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


from agents.model_config import create_chat_model_from_config


def _parse_highlights_and_risks(raw: str) -> tuple[list[str], list[str]]:
    """从 ReAgent 返回的文本中解析【要点】与【风险提示】。"""
    highlights: list[str] = []
    risk_tips: list[str] = []
    in_risks = False
    for line in (raw or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if "【风险提示】" in line or (line == "风险提示") or (line.startswith("风险提示") and "：" not in line):
            in_risks = True
            line = line.replace("【风险提示】", "").replace("风险提示", "").strip()
        elif "【要点】" in line or line == "要点" or line.startswith("要点"):
            in_risks = False
            line = line.replace("【要点】", "").strip()
        if line.startswith("-") or line.startswith("•"):
            line = line.lstrip("-• ").strip()
        if not line:
            continue
        if in_risks:
            risk_tips.append(line)
        else:
            highlights.append(line)
    return highlights[:8], risk_tips[:6]


async def _highlights_and_risks_via_reagent(
    product_name: str,
    elements: ProductElements,
    retrieval_context: str = "",
) -> tuple[list[str], list[str]]:
    """通过 AgentScope ReActAgent（ReAgent）生成结构化要点与风险提示。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return [], []
    model = create_chat_model_from_config()
    if model is None:
        return [], []
    d = elements.to_dict()
    elem_text = "\n".join(
        f"- {k}: {v}" for k, v in d.items()
        if v is not None and (str(v).strip() if not isinstance(v, dict) else True)
    )
    if not elem_text.strip():
        elem_text = "（未从文档中抽到结构化要素）"
    sys_prompt = """你是金融产品解读助手。根据产品要素与可选参考信息，输出两项内容：
1) 结构化要点：3～6 条，每条一句话，涵盖期限、收益特征、投向、费率等关键信息；
2) 风险提示：2～4 条，明确该产品的主要风险点。
请严格按以下格式输出，不要其他说明：
【要点】
- 要点1
- 要点2
【风险提示】
- 风险1
- 风险2"""
    user_content = f"产品名称：{product_name or '未知'}\n\n产品要素：\n{elem_text}"
    if retrieval_context:
        user_content += f"\n\n参考资料：\n{retrieval_context[:2000]}"
    user_content += "\n\n请输出【要点】和【风险提示】。"
    agent = ReActAgent(
        name="ProductInterpretAgent",
        sys_prompt=sys_prompt,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=Toolkit(),
    )
    msg_res = await agent(Msg("user", user_content, "user"))
    if msg_res is None:
        return [], []
    text = msg_res.get_text_content() if hasattr(msg_res, "get_text_content") else None
    if not text and hasattr(msg_res, "get_content_blocks"):
        blocks = msg_res.get_content_blocks("text")
        if blocks:
            text = "\n".join(getattr(b, "text", b.get("text", "")) for b in blocks)
    return _parse_highlights_and_risks((text or "").strip())


def query_product_interpret(
    product_id: str,
    permission_context: dict[str, Any] | None = None,
    use_retrieval: bool = False,
    use_reagent: bool = True,
) -> dict[str, Any]:
    """
    Data Access 取产品 → 要素抽取 → 可选 Retrieval → AgentScope ReActAgent 生成要点与风险提示。

    Returns:
        product: 产品基础信息（含 name/id）
        elements: 抽取的要素 dict
        highlights: list[str] 结构化要点
        risk_tips: list[str] 风险提示
        answer: str 汇总文本，便于展示
    """
    product_id = (product_id or "").strip()
    if not product_id:
        return {
            "product": None,
            "elements": {},
            "highlights": [],
            "risk_tips": [],
            "answer": "请提供产品 ID。",
        }
    product = _get_product_by_id(product_id, permission_context)
    if not product:
        return {
            "product": None,
            "elements": {},
            "highlights": [],
            "risk_tips": [],
            "answer": f"未找到产品（id: {product_id}），或无权访问。",
        }
    text = _text_from_product(product)
    elements = extract_elements(text, use_llm=True)
    product_name = product.get("name") or product.get("product_name") or product_id
    retrieval_context = ""
    if use_retrieval:
        try:
            from retrieval.service import retrieve
            ret = retrieve(query=f"{product_name} 风险 收益 条款", top_k=3)
            if ret.chunks:
                retrieval_context = "\n".join(c.get("chunk_text", "") or "" for c in ret.chunks[:3])
        except Exception:
            pass
    highlights: list[str] = []
    risk_tips: list[str] = []
    if use_reagent:
        try:
            highlights, risk_tips = asyncio.run(_highlights_and_risks_via_reagent(product_name, elements, retrieval_context))
        except Exception:
            pass
    if not highlights and not risk_tips:
        highlights = [f"期限：{elements.term or '—'}", f"风险等级：{elements.risk_level or '—'}", f"费率：{elements.fee_rate or '—'}"]
        risk_tips = ["请以产品说明书与销售文件为准，投资有风险。"]
    lines = ["【要点】"] + [f"- {h}" for h in highlights] + ["【风险提示】"] + [f"- {r}" for r in risk_tips]
    answer = "\n".join(lines)
    return {
        "product": {"id": product_id, "name": product_name},
        "elements": elements.to_dict(),
        "highlights": highlights,
        "risk_tips": risk_tips,
        "answer": answer,
    }


async def product_interpret_query(product_id: str) -> Any:
    """
    产品解读，包装为 ToolResponse。供 toolkit.register_tool_function(product_interpret_query) 注册。
    内部通过 ReActAgent 生成要点与风险提示。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    result = query_product_interpret((product_id or "").strip())
    text = result.get("answer") or "无法生成解读。"
    return ToolResponse(content=[TextBlock(type="text", text=text)])
