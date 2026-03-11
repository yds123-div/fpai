# -*- coding: utf-8 -*-
"""
报告生成智能体：周报/月报/市场解读稿；Retrieval + Data Access + 模板 + ReAgent。

T022：向 AgentScope 注册为工具 report_generate_query；见 technical_design §2.2 reportBlocks、citations。
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from data_access import get_data
from retrieval.service import retrieve
from retrieval.types import Citation

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

# T014 报告模板 config_key；无则使用默认结构
CONFIG_KEY_REPORT_TEMPLATE = "report_template"
DEFAULT_REPORT_SECTIONS = ["标题", "摘要", "要点", "风险提示", "参考来源"]


def _get_report_template() -> str:
    """从 config（T014）读取报告模板结构，无则返回默认。"""
    try:
        from config import get_config
    except ImportError:
        return _default_template_text()
    data = get_config(CONFIG_KEY_REPORT_TEMPLATE, use_cache=True)
    if not data or not isinstance(data, dict):
        return _default_template_text()
    sections = data.get("sections") or data.get("structure")
    if isinstance(sections, list) and sections:
        return "报告须包含以下部分：\n" + "\n".join(f"- {s}" for s in sections)
    return _default_template_text()


def _default_template_text() -> str:
    return "报告须包含以下部分：\n- 标题\n- 摘要\n- 要点（3～5 条）\n- 风险提示（2～4 条）\n- 参考来源"


from agents.model_config import create_chat_model_from_config


async def _generate_report_via_reagent(
    demand: str,
    retrieval_refs: str,
    data_access_summary: str,
    template_text: str,
) -> str | None:
    """用 ReActAgent 根据需求、检索资料与可选数据摘要生成报告正文。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return None
    model = create_chat_model_from_config()
    if model is None:
        return None
    sys_prompt = """你是财富/市场报告撰写助手。根据用户报告需求与参考资料，按给定结构撰写报告。
输出须包含：标题、摘要、要点（3～5 条）、风险提示（2～4 条）、参考来源。语言专业、客观，不编造未在资料中出现的数据。"""
    user_parts = [f"报告需求：{demand}", "参考资料：", retrieval_refs]
    if data_access_summary:
        user_parts.append("相关产品/数据摘要：")
        user_parts.append(data_access_summary)
    user_parts.append("请按以下结构输出：")
    user_parts.append(template_text)
    user_content = "\n\n".join(user_parts)
    agent = ReActAgent(
        name="ReportGenerateAgent",
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


def _parse_report_blocks(raw: str) -> list[dict[str, str]]:
    """将 ReAgent 输出解析为 reportBlocks：[{type, content}]。"""
    blocks: list[dict[str, str]] = []
    if not raw or not raw.strip():
        return blocks
    section_patterns = [
        (r"【?标题】?\s*[\n\r]+([^\n\r]+)", "标题"),
        (r"【?摘要】?\s*[\n\r]+([\s\S]*?)(?=【?要点】|【?风险提示】|【?参考来源】|$)", "摘要"),
        (r"【?要点】?\s*[\n\r]+([\s\S]*?)(?=【?风险提示】|【?参考来源】|$)", "要点"),
        (r"【?风险提示】?\s*[\n\r]+([\s\S]*?)(?=【?参考来源】|$)", "风险提示"),
        (r"【?参考来源】?\s*[\n\r]+([\s\S]*)", "参考来源"),
    ]
    for pattern, block_type in section_patterns:
        m = re.search(pattern, raw, re.IGNORECASE)
        if m:
            content = m.group(1).strip()
            if content:
                blocks.append({"type": block_type, "content": content})
    if not blocks:
        blocks.append({"type": "正文", "content": raw.strip()})
    return blocks


def query_report_generate(
    demand: str,
    permission_context: dict[str, Any] | None = None,
    use_retrieval: bool = True,
    use_data_access: bool = True,
    use_reagent: bool = True,
    retrieval_top_k: int = 10,
) -> dict[str, Any]:
    """
    周报/月报/市场解读稿生成：Retrieval 取参考资料 + 可选 Data Access 产品摘要 + 模板 + ReAgent。

    Args:
        demand: 报告类型或需求描述（如「周报」「月报」「市场解读 本周」）。
        permission_context: 权限上下文。
        use_retrieval: 是否调用 retrieval 检索资料。
        use_data_access: 是否拉取产品摘要作为补充。
        use_reagent: 是否用 ReAgent 生成报告。
        retrieval_top_k: 检索条数。

    Returns:
        report_blocks: list[{type, content}] 标题/摘要/要点/风险提示/参考来源
        citations: 检索引用列表
        answer: 完整报告文本
    """
    demand = (demand or "").strip() or "财富周报/市场解读"
    retrieval_refs = ""
    citations: list[Citation] = []
    if use_retrieval:
        try:
            ret = retrieve(
                query=demand,
                top_k=retrieval_top_k,
                permission_context=permission_context,
            )
            if ret.chunks:
                retrieval_refs = "\n\n".join(
                    f"[{i+1}] {(c.get('chunk_text') or '')[:600]}"
                    for i, c in enumerate(ret.chunks[:10])
                )
                citations = list(ret.citations)
        except Exception:
            pass
    if not retrieval_refs:
        retrieval_refs = "（暂无检索到相关资料，将基于通用知识生成概要结构。）"
    data_access_summary = ""
    if use_data_access:
        try:
            records, _ = get_data(
                model_code="products",
                request_params={"page": 1, "page_size": 5},
                permission_context=permission_context,
            )
            if records:
                lines = []
                for i, p in enumerate(records[:5], 1):
                    name = p.get("name") or p.get("product_name") or p.get("id") or ""
                    lines.append(f"{i}. {name}")
                data_access_summary = "\n".join(lines)
        except Exception:
            pass
    template_text = _get_report_template()
    report_text = ""
    if use_reagent:
        try:
            report_text = asyncio.run(
                _generate_report_via_reagent(demand, retrieval_refs, data_access_summary, template_text)
            ) or ""
        except Exception:
            pass
    if not report_text:
        report_text = (
            f"【标题】{demand} 报告\n\n"
            "【摘要】根据当前需求暂无法生成完整报告内容，请确认检索与模型服务可用，或稍后重试。\n\n"
            "【风险提示】报告内容仅供参考，不构成投资建议。"
        )
    report_blocks = _parse_report_blocks(report_text)
    return {
        "report_blocks": report_blocks,
        "citations": citations,
        "answer": report_text,
    }


async def report_generate_query(demand: str) -> Any:
    """
    报告生成，包装为 ToolResponse。供 toolkit.register_tool_function(report_generate_query) 注册。

    Args:
        demand: 报告类型或需求描述（如「周报」「月报」「市场解读」）。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    result = query_report_generate((demand or "").strip())
    text = result.get("answer") or "无法生成报告。"
    return ToolResponse(content=[TextBlock(type="text", text=text)])
