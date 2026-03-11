# -*- coding: utf-8 -*-
"""
编排器与 AgentScope 集成：意图与槽位注入、ReAct 主智能体 + Toolkit、合规审查与审计落库。

T026：见 architecture、technical_design §2.5；供 POST /chat 等调用。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from pkg.logger import get_logger

from orchestrator.intent_slot import detect_intent_and_slots, IntentSlotResult

logger = get_logger(__name__)

try:
    from agentscope.message import Msg
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    Msg = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False


@dataclass
class ChatTurnResult:
    """单轮编排结果，与 chat API 契约对齐。"""
    answer_id: str = ""
    answer_blocks: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    compliance: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    suggested_questions: list[str] = field(default_factory=list)
    intent: str = ""
    slots: dict[str, Any] = field(default_factory=dict)


def _extract_text_from_response(msg: Any) -> str:
    """从 AgentScope 返回的 Msg 中提取文本。"""
    if msg is None:
        return ""
    text = getattr(msg, "get_text_content", None)
    if callable(text):
        out = text()
        if out:
            return (out or "").strip()
    if hasattr(msg, "content") and isinstance(msg.content, list):
        parts = []
        for block in msg.content:
            if hasattr(block, "text"):
                parts.append(block.text or "")
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", "") or "")
        return "\n".join(parts).strip()
    return str(getattr(msg, "content", "") or "").strip()


async def _run_agent_turn(
    message: str,
    intent_slot: IntentSlotResult,
    permission_context: dict[str, Any] | None,
) -> str:
    """调用 ReAct 路由智能体执行一轮，返回回复文本。"""
    if not _AGENTSCOPE_AVAILABLE or Msg is None:
        return ""
    from agents.routing.implicit import get_implicit_router
    router = get_implicit_router()
    if router is None:
        return ""
    context_fragment = intent_slot.to_context_prompt_fragment()
    user_content = f"{context_fragment}\n\n用户消息：{message}"
    try:
        response = await router(Msg("user", user_content, "user"))
        return _extract_text_from_response(response)
    except Exception as e:
        logger.warning("AgentScope 路由执行异常: %s", e)
        return ""


def _ensure_compliance_and_audit(
    answer_id: str,
    message: str,
    reply_text: str,
    intent_slot: IntentSlotResult,
    compliance_input: Any,
    compliance_output: Any,
    session_id: str | None,
    user_id: str | None,
) -> dict[str, Any]:
    """写入审计事件（意图、合规输入/输出、回复摘要）；返回 compliance 字段用 dict。"""
    compliance_payload = (
        compliance_output.to_dict() if compliance_output and hasattr(compliance_output, "to_dict")
        else {"action": "pass"}
    )
    try:
        from audit import append_event
        append_event(
            answer_id,
            "intent_slot",
            {"intent": intent_slot.intent, "slots": intent_slot.slots},
            session_id=session_id,
            user_id=user_id,
            intent=intent_slot.intent,
        )
        inp_payload = (
            compliance_input.to_dict() if compliance_input and hasattr(compliance_input, "to_dict")
            else {"action": str(getattr(compliance_input, "action", "pass"))}
        )
        append_event(
            answer_id,
            "compliance_input",
            inp_payload,
            session_id=session_id,
            user_id=user_id,
            policy_version=inp_payload.get("policy_version"),
        )
        append_event(
            answer_id,
            "compliance_output",
            compliance_payload,
            session_id=session_id,
            user_id=user_id,
            policy_version=compliance_payload.get("policy_version"),
        )
        append_event(
            answer_id,
            "reply",
            {"answer_blocks_count": 1, "preview": (reply_text or "")[:200]},
            session_id=session_id,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning("审计落库失败: %s", e)
    return compliance_payload


async def run_chat_turn_async(
    message: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    product_ids: list[str] | None = None,
    customer_profile: str | None = None,
    permission_context: dict[str, Any] | None = None,
    answer_id: str | None = None,
    trace_id: str | None = None,
    use_intent_slot: bool = True,
    use_compliance: bool = True,
    use_audit: bool = True,
) -> ChatTurnResult:
    """
    执行一轮对话编排：意图与槽位抽取 → 注入 AgentScope → ReAct+Toolkit 执行 → 合规审查 → 审计落库。

    Args:
        message: 用户输入。
        session_id: 会话 ID。
        user_id: 用户 ID（审计与合规用）。
        product_ids: 会话内已选产品 ID，参与槽位回填。
        customer_profile: 会话内客户画像，参与槽位回填。
        permission_context: 权限上下文（产品池等），传给智能体/检索。
        answer_id: 若提供则复用，否则生成。
        trace_id: 链路 ID。
        use_intent_slot: 是否做意图与槽位抽取。
        use_compliance: 是否做输入/输出合规审查。
        use_audit: 是否落审计。

    Returns:
        ChatTurnResult: answer_blocks、citations、compliance、trace、suggested_questions 等。
    """
    result = ChatTurnResult(
        answer_id=answer_id or uuid.uuid4().hex,
        trace={"traceId": trace_id or uuid.uuid4().hex},
    )
    message = (message or "").strip()
    if not message:
        result.answer_blocks = [""]
        result.compliance = {"action": "pass", "reason": "空输入"}
        return result

    # 1) 意图与槽位
    intent_slot = IntentSlotResult(intent="other", slots={})
    if use_intent_slot:
        context = {}
        if product_ids:
            context["productIds"] = product_ids
        if customer_profile:
            context["customerProfile"] = customer_profile
        intent_slot = detect_intent_and_slots(message, context=context or None, use_llm=True)
    result.intent = intent_slot.intent
    result.slots = dict(intent_slot.slots)
    result.trace["intent"] = intent_slot.intent

    # 2) 输入合规
    compliance_input = None
    if use_compliance:
        try:
            from compliance import check_input
            compliance_input = check_input(message, user_id=user_id)
            if not getattr(compliance_input, "is_allowed", lambda: True)():
                result.answer_blocks = [getattr(compliance_input, "suggestion", None) or "抱歉，该输入未通过合规检查，请修改后重试。"]
                result.compliance = compliance_input.to_dict() if hasattr(compliance_input, "to_dict") else {"action": "reject"}
                if use_audit:
                    _ensure_compliance_and_audit(
                        result.answer_id, message, "", intent_slot,
                        compliance_input, compliance_input,
                        session_id, user_id,
                    )
                return result
        except Exception as e:
            logger.warning("合规输入审查异常: %s", e)

    # 3) AgentScope 执行
    reply_text = await _run_agent_turn(message, intent_slot, permission_context)
    if not reply_text:
        reply_text = "当前无法生成回复，请稍后重试或换一种方式提问。"

    # 4) 输出合规
    compliance_output = None
    if use_compliance:
        try:
            from compliance import check_output
            compliance_output = check_output(reply_text, citations=result.citations)
            result.compliance = compliance_output.to_dict() if hasattr(compliance_output, "to_dict") else {}
            if not getattr(compliance_output, "is_allowed", lambda: True)():
                reply_text = getattr(compliance_output, "suggestion", None) or "回复未通过合规审查，建议转人工确认。"
                result.answer_blocks = [reply_text]
            else:
                result.answer_blocks = [reply_text]
        except Exception as e:
            logger.warning("合规输出审查异常: %s", e)
            result.answer_blocks = [reply_text]
            result.compliance = {"action": "pass", "reason": "审查异常降级通过"}
    else:
        result.answer_blocks = [reply_text]
        result.compliance = {"action": "pass"}

    # 5) 审计
    if use_audit:
        _ensure_compliance_and_audit(
            result.answer_id, message, reply_text, intent_slot,
            compliance_input, compliance_output or compliance_input,
            session_id, user_id,
        )

    return result


def run_chat_turn(
    message: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    product_ids: list[str] | None = None,
    customer_profile: str | None = None,
    permission_context: dict[str, Any] | None = None,
    answer_id: str | None = None,
    trace_id: str | None = None,
    use_intent_slot: bool = True,
    use_compliance: bool = True,
    use_audit: bool = True,
) -> ChatTurnResult:
    """同步封装：asyncio.run(run_chat_turn_async(...))。"""
    return asyncio.run(
        run_chat_turn_async(
            message,
            session_id=session_id,
            user_id=user_id,
            product_ids=product_ids,
            customer_profile=customer_profile,
            permission_context=permission_context,
            answer_id=answer_id,
            trace_id=trace_id,
            use_intent_slot=use_intent_slot,
            use_compliance=use_compliance,
            use_audit=use_audit,
        )
    )
