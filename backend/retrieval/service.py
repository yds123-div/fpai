"""
检索服务：Embedding 向量化 query → Milvus 召回 → Reranker 精排 → ReAgent 生成回答（T009）。
权限上下文过滤、citations 输出；见 technical_design §3.3。生成回答优先 AgentScope ReActAgent，回退 model_gateway.llm_chat。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from pkg.milvus_client import (
    search_with_filter,
    FIELD_CHUNK_TEXT,
    FIELD_DOC_ID,
    FIELD_SOURCE,
)
from model_gateway import embed, rerank, llm_chat, ModelNotConfiguredError

from retrieval.types import Citation, RetrieveResult, GenerateAnswerResult

try:
    from agentscope.tool import Toolkit
    from agentscope.agent import ReActAgent
    from agentscope.formatter import DashScopeChatFormatter
    from agentscope.memory import InMemoryMemory
    from agentscope.message import Msg
    from agentscope.model import OpenAIChatModel, DashScopeChatModel
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    Toolkit = None  # type: ignore[misc, assignment]
    ReActAgent = None  # type: ignore[misc, assignment]
    DashScopeChatFormatter = None  # type: ignore[misc, assignment]
    InMemoryMemory = None  # type: ignore[misc, assignment]
    Msg = None  # type: ignore[misc, assignment]
    OpenAIChatModel = None  # type: ignore[misc, assignment]
    DashScopeChatModel = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False


# 召回阶段多取一些，供 Reranker 精排后取 top_k
RERANK_OVER_FETCH = 3


def _create_chat_model_from_config():
    """从 model_gateway.config 读取 LLM，供 ReActAgent 使用；与 agents/faq 逻辑一致。"""
    if not _AGENTSCOPE_AVAILABLE or (OpenAIChatModel is None and DashScopeChatModel is None):
        return None
    try:
        from model_gateway.config import load_gateway_config
    except ImportError:
        return None
    cfg = load_gateway_config()
    llm = cfg.llm
    base_url = (llm.base_url or "").strip()
    api_key = (llm.api_key or "").strip()
    generate_kwargs = {"temperature": llm.temperature, "max_tokens": llm.max_tokens}
    if base_url:
        return OpenAIChatModel(
            model_name=llm.model or "qwen3",
            api_key=api_key or None,
            stream=False,
            client_kwargs={"base_url": base_url},
            generate_kwargs=generate_kwargs,
            enable_thinking=False,
        )
    if api_key:
        return DashScopeChatModel(
            model_name=llm.model or "qwen-max",
            api_key=api_key,
            stream=False,
            generate_kwargs=generate_kwargs,
            enable_thinking=False,
        )
    dash_key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if dash_key:
        return DashScopeChatModel(
            model_name=llm.model or "qwen-max",
            api_key=dash_key,
            stream=False,
            generate_kwargs=generate_kwargs,
            enable_thinking=False,
        )
    return None


async def _generate_answer_via_reagent(query: str, refs: str) -> str | None:
    """用 AgentScope ReActAgent（无工具）基于参考片段生成回答。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return None
    model = _create_chat_model_from_config()
    if model is None:
        return None
    sys_prompt = (
        "基于给定的参考片段回答用户问题。若参考中无相关内容，请说明无法从给定资料中得出答案。"
        "请直接给出回答，并在适当处标注引用序号 [1][2] 等。"
    )
    user_content = f"参考片段：\n{refs}\n\n用户问题：{query}\n请回答："
    agent = ReActAgent(
        name="RetrievalAnswerAgent",
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


def _permission_filter_expr(permission_context: dict[str, Any] | None) -> str | None:
    """根据权限上下文构造 Milvus filter 表达式。"""
    if not permission_context:
        return None
    tags = permission_context.get("permission_tags") or permission_context.get("product_pool_ids")
    if not tags:
        return None
    if isinstance(tags, str):
        tags = [tags]
    quoted = [f'"{t}"' for t in tags]
    return f"permission_tag in [{','.join(quoted)}]"


def _normalize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """兼容 pymilvus 返回的 entity 包裹或扁平 dict。"""
    entity = hit.get("entity") or hit
    return {
        "id": hit.get("id") or entity.get("id"),
        "doc_id": entity.get(FIELD_DOC_ID) or "",
        "source": entity.get(FIELD_SOURCE) or "",
        "chunk_text": entity.get(FIELD_CHUNK_TEXT) or "",
        "permission_tag": entity.get("permission_tag") or "",
        "distance": hit.get("distance", 0.0),
    }


def retrieve(
    query: str,
    filters: dict[str, Any] | None = None,
    top_k: int = 10,
    permission_context: dict[str, Any] | None = None,
    use_reranker: bool = True,
) -> RetrieveResult:
    """
    Embedding 向量化 query → Milvus 召回（按权限过滤）→ 可选 Reranker 精排 → 返回 chunks、scores、citations。
    """
    chunks: list[dict[str, Any]] = []
    scores: list[float] = []
    citations: list[Citation] = []

    try:
        query_vectors = embed([query])
    except ModelNotConfiguredError:
        return RetrieveResult(chunks=[], scores=[], citations=[])
    if not query_vectors or not query_vectors[0]:
        return RetrieveResult(chunks=[], scores=[], citations=[])

    filter_expr = _permission_filter_expr(permission_context)
    limit = top_k * RERANK_OVER_FETCH if use_reranker else top_k
    raw = search_with_filter(
        query_vectors=[query_vectors[0]],
        filter_expr=filter_expr,
        top_k=limit,
        output_fields=[FIELD_DOC_ID, FIELD_SOURCE, FIELD_CHUNK_TEXT],
    )
    if not raw or not raw[0]:
        return RetrieveResult(chunks=[], scores=[], citations=[])

    hits = [_normalize_hit(h) for h in raw[0]]
    if not hits:
        return RetrieveResult(chunks=[], scores=[], citations=[])

    if use_reranker and len(hits) > 1:
        try:
            doc_texts = [h["chunk_text"] for h in hits]
            rerank_scores = rerank(query, doc_texts)
            if len(rerank_scores) == len(hits):
                paired = list(zip(hits, rerank_scores, strict=False))
                paired.sort(key=lambda x: x[1], reverse=True)
                hits = [p[0] for p in paired[:top_k]]
                rerank_scores = [p[1] for p in paired[:top_k]]
            else:
                hits = hits[:top_k]
                rerank_scores = [h.get("distance", 0.0) for h in hits]
        except ModelNotConfiguredError:
            hits = hits[:top_k]
            rerank_scores = [h.get("distance", 0.0) for h in hits]
    else:
        hits = hits[:top_k]
        rerank_scores = [h.get("distance", 0.0) for h in hits]

    for h, sc in zip(hits, rerank_scores, strict=False):
        chunks.append(h)
        scores.append(float(sc))
        citations.append(
            Citation(doc_id=h["doc_id"], source=h["source"], chunk_text=h["chunk_text"], score=float(sc))
        )

    return RetrieveResult(chunks=chunks, scores=scores, citations=citations)


def generate_answer(
    query: str,
    chunks: list[dict[str, Any]],
    citations: list[Citation] | None = None,
    use_reagent: bool = True,
) -> GenerateAnswerResult:
    """
    基于检索得到的 chunks 生成回答（T009：优先 ReAgent，回退 llm_chat）；返回 answerBlocks 与 citations。
    若 use_reagent=True 且 AgentScope 可用则用 ReActAgent；否则或失败时用 model_gateway.llm_chat。
    """
    if not chunks:
        return GenerateAnswerResult(answer_blocks=[""], citations=[])

    refs = "\n\n".join(
        f"[{i+1}] {(c.get('chunk_text') or '')[:500]}..."
        for i, c in enumerate(chunks[:10])
    )
    blocks: list[str] = []

    if use_reagent:
        try:
            content = asyncio.run(_generate_answer_via_reagent(query, refs))
            if content:
                blocks = [content]
        except Exception:
            pass

    if not blocks:
        prompt = f"""基于以下参考片段回答用户问题。若参考中无相关内容，请说明无法从给定资料中得出答案。

参考片段：
{refs}

用户问题：{query}

请直接给出回答，并在适当处标注引用序号 [1][2] 等。"""
        try:
            content = llm_chat([{"role": "user", "content": prompt}])
            blocks = [content.strip()] if content else [""]
        except ModelNotConfiguredError:
            blocks = ["[检索完成，但 LLM 未配置，无法生成回答]"]

    ref_list: list[Citation] = list(citations) if citations else [
        Citation(doc_id=c.get("doc_id", ""), source=c.get("source", ""), chunk_text=c.get("chunk_text", ""), score=0.0)
        for c in chunks
    ]
    return GenerateAnswerResult(answer_blocks=blocks, citations=ref_list)
