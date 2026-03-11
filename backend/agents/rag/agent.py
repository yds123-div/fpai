# -*- coding: utf-8 -*-
"""
RAG 智能体：调用 retrieval 检索 + 生成，输出 answer_blocks 与 citations。

T017：向 AgentScope 注册为工具 rag_query；供路由等 toolkit 使用。
"""
from __future__ import annotations

from typing import Any

from retrieval.service import retrieve, generate_answer
from retrieval.types import Citation

try:
    from agentscope.tool import ToolResponse
    from agentscope.message import TextBlock
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    ToolResponse = None  # type: ignore[misc, assignment]
    TextBlock = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False


def query_rag(
    query: str,
    top_k: int = 10,
    permission_context: dict[str, Any] | None = None,
    use_reranker: bool = True,
) -> dict[str, Any]:
    """
    调用 retrieval 检索 + 生成，返回 answer_blocks 与 citations。

    Returns:
        answer_blocks: list[str]
        citations: list[dict] (doc_id, source, chunk_text, score)
        answer: str（首块拼接，便于单文本展示）
    """
    query = (query or "").strip()
    if not query:
        return {"answer_blocks": [], "citations": [], "answer": ""}
    ret = retrieve(
        query=query,
        top_k=top_k,
        permission_context=permission_context,
        use_reranker=use_reranker,
    )
    if not ret.chunks:
        return {
            "answer_blocks": ["未检索到相关片段。"],
            "citations": [],
            "answer": "未检索到相关片段。",
        }
    gen = generate_answer(
        query=query,
        chunks=ret.chunks,
        citations=ret.citations,
    )
    citations_dict = [
        {
            "doc_id": c.doc_id,
            "source": c.source,
            "chunk_text": (c.chunk_text or "")[:200],
            "score": c.score,
        }
        for c in gen.citations
    ]
    answer = "\n".join(b for b in gen.answer_blocks if b).strip() or ""
    return {
        "answer_blocks": gen.answer_blocks,
        "citations": citations_dict,
        "answer": answer,
    }


async def rag_query(query: str) -> Any:
    """
    RAG 检索与生成，包装为 ToolResponse。供 toolkit.register_tool_function(rag_query) 注册。

    Args:
        query: 用户检索/提问内容。

    Returns:
        ToolResponse: 包含回答文本与引用说明；未安装 agentscope 时抛出 RuntimeError。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    result = query_rag((query or "").strip(), top_k=10)
    text = result.get("answer") or result.get("answer_blocks", [""])[0] or "未检索到相关片段。"
    if result.get("citations"):
        refs = "; ".join(
            (c.get("source") or c.get("doc_id") or "")[:40]
            for c in result["citations"][:5]
        )
        text += "\n\n参考：" + refs
    return ToolResponse(content=[TextBlock(type="text", text=text)])
