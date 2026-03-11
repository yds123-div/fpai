# -*- coding: utf-8 -*-
"""
猜你想问/洞察智能体：会话上下文 + ReAgent 生成 suggestedQuestions[]。

T023：向 AgentScope 注册为工具 insight_query；供 chat 响应或 done 事件返回推荐问题列表。
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

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

DEFAULT_MAX_QUESTIONS = 5


async def _suggested_questions_via_reagent(context: str, max_questions: int) -> list[str]:
    """用 ReActAgent 根据会话/页面上下文生成推荐追问列表。"""
    if not _AGENTSCOPE_AVAILABLE or ReActAgent is None or Toolkit is None:
        return []
    model = create_chat_model_from_config()
    if model is None:
        return []
    sys_prompt = (
        "你是对话助手。根据用户当前的对话或页面上下文，生成若干条用户可能追问的推荐问题。"
        "要求：简短、具体、与上下文相关；仅输出问题列表，每行一个问题，不要编号或其它说明。"
    )
    user_content = f"上下文：\n{context}\n\n请输出 {max_questions} 条以内的推荐问题，每行一个。"
    agent = ReActAgent(
        name="InsightAgent",
        sys_prompt=sys_prompt,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=Toolkit(),
    )
    msg_res = await agent(Msg("user", user_content, "user"))
    if msg_res is None:
        return []
    text = msg_res.get_text_content() if hasattr(msg_res, "get_text_content") else None
    if not text and hasattr(msg_res, "get_content_blocks"):
        blocks = msg_res.get_content_blocks("text")
        if blocks:
            text = "\n".join(getattr(b, "text", b.get("text", "")) for b in blocks)
    return _parse_suggested_questions((text or "").strip(), max_questions)


def _parse_suggested_questions(raw: str, max_questions: int) -> list[str]:
    """从模型输出解析出问题列表：按行切分，去掉编号与空行。"""
    if not raw or not raw.strip():
        return []
    questions: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[\.\、)\]]\s*", "", line).strip()
        if line and len(questions) < max_questions:
            questions.append(line)
    return questions[:max_questions]


def query_insight(
    context: str,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
    use_reagent: bool = True,
) -> dict[str, Any]:
    """
    根据会话或页面上下文生成推荐追问（suggestedQuestions）。

    Args:
        context: 当前会话摘要、最近几轮消息或页面上下文。
        max_questions: 最多返回几条推荐问题。
        use_reagent: 是否用 ReAgent 生成。

    Returns:
        suggested_questions: list[str] 推荐问题列表，供 chat 响应 suggestedQuestions[]。
        answer: 格式化文本，便于工具返回展示。
    """
    context = (context or "").strip()
    if not context:
        return {
            "suggested_questions": [],
            "answer": "请提供会话或页面上下文以生成推荐问题。",
        }
    max_questions = max(1, min(max_questions, 10))
    suggested_questions: list[str] = []
    if use_reagent:
        try:
            suggested_questions = asyncio.run(_suggested_questions_via_reagent(context, max_questions))
        except Exception:
            pass
    if not suggested_questions:
        suggested_questions = [
            "能否再详细说明一下？",
            "有没有相关产品可以推荐？",
            "风险方面需要注意什么？",
        ][:max_questions]
    answer = "【猜你想问】\n\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(suggested_questions))
    return {
        "suggested_questions": suggested_questions,
        "answer": answer,
    }


async def insight_query(context: str) -> Any:
    """
    猜你想问/洞察，包装为 ToolResponse。供 toolkit.register_tool_function(insight_query) 注册。

    Args:
        context: 当前会话或页面上下文。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    result = query_insight((context or "").strip())
    text = result.get("answer") or "暂无推荐问题。"
    return ToolResponse(content=[TextBlock(type="text", text=text)])
