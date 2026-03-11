"""
FAQ 问答智能体：检索层 TopK 相似 FAQ → 初始化 AgentScope 调用返回答案。

逻辑：1）检索层 search_faq(question, top_k) 得到 TopK 相似 FAQ；
     2）用检索结果构建上下文，初始化 AgentScope（ReActAgent + 统一模型配置）生成回答；
     3）返回 answer_blocks、citations。对外工具 faq_query 包装为 ToolResponse。
"""
from __future__ import annotations

import asyncio
from typing import Any

from agents.faq.retrieval import search_faq
from agents.faq.store import FAQHit

logger = __import__("pkg.logger", fromlist=["get_logger"]).get_logger(__name__)

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

from agents.model_config import create_chat_model_from_config


def _build_faq_context(matches: list[FAQHit]) -> str:
    """将 TopK FAQ 拼成给 AgentScope 的上下文。"""
    parts = []
    for i, m in enumerate(matches, 1):
        parts.append(f"【{i}】问：{m.question}\n答：{m.answer}")
    return "\n\n".join(parts)


async def _answer_via_agentscope(question: str, context: str) -> str | None:
    """用 AgentScope ReActAgent（无工具，仅系统提示+用户问）生成答案。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return None
    model = create_chat_model_from_config()
    if model is None:
        return None
    sys_prompt = (
        "你是客服助手。根据以下 FAQ 标准问答，用简洁自然的语言回答用户问题。"
        "若 FAQ 中有直接答案可引用，并说明来源；不要编造 FAQ 中未出现的信息。"
    )
    user_content = f"参考 FAQ：\n{context}\n\n用户问题：{question}\n请回答："
    agent = ReActAgent(
        name="FAQAgent",
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


def query_faq(question: str, top_k: int = 5, use_llm: bool = True) -> dict[str, Any]:
    """
    1）检索层 TopK 相似 FAQ；2）初始化 AgentScope 调用返回答案。
    无 AgentScope/模型配置时回退 model_gateway.llm_chat 或首条标准答。
    返回：hit、answer、answer_blocks、citations、matches。
    """
    question = (question or "").strip()
    matches = search_faq(question, top_k=top_k)
    if not matches:
        return {
            "hit": False,
            "answer": "",
            "answer_blocks": [],
            "citations": [],
            "matches": [],
        }
    citations = [{"question": m.question, "answer": m.answer, "id": m.id} for m in matches]
    if not use_llm:
        best = matches[0]
        return {
            "hit": True,
            "answer": best.answer,
            "answer_blocks": [{"type": "text", "text": best.answer}],
            "citations": citations,
            "matches": [m.to_dict() for m in matches],
        }

    context = _build_faq_context(matches)
    answer = None
    try:
        answer = asyncio.run(_answer_via_agentscope(question, context))
    except Exception as e:
        logger.warning("FAQ AgentScope 调用异常: %s", e)
    if answer:
        return {
            "hit": True,
            "answer": answer,
            "answer_blocks": [{"type": "text", "text": answer}],
            "citations": citations,
            "matches": [m.to_dict() for m in matches],
        }

    # 回退：首条标准答
    best = matches[0]
    return {
        "hit": True,
        "answer": best.answer,
        "answer_blocks": [{"type": "text", "text": best.answer}],
        "citations": citations,
        "matches": [m.to_dict() for m in matches],
    }


# ----- 对外工具：供路由等注册，返回 ToolResponse -----

async def faq_query(question: str) -> Any:
    """
    在 FAQ 知识库中检索并回答（检索 TopK → AgentScope 返回答案），包装为 ToolResponse。
    供 toolkit.register_tool_function(faq_query) 注册。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    result = query_faq((question or "").strip(), top_k=5)
    text = result.get("answer") or "未找到匹配的 FAQ。"
    if result.get("citations"):
        refs = "; ".join((c.get("question") or "")[:30] for c in result["citations"][:5])
        text += "\n\n参考：" + refs
    return ToolResponse(content=[TextBlock(type="text", text=text)])
