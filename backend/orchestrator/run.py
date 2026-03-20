# -*- coding: utf-8 -*-
"""
编排器与 AgentScope 集成：意图与槽位注入、ReAct 主智能体 + Toolkit、合规审查与审计落库。

T026：见 architecture、technical_design §2.5；供 POST /chat 等调用。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from pkg.logger import get_logger

# 基金业务 Agent 框架 fund_agent_framework（Coordinator 规划 → 多任务执行/融合 → 业务 agent）
from agents.fund_agent_framework import FundAgentRouter, AgentRunContext

logger = get_logger(__name__)

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


def _strip_think_blocks(text: str, *, show_thinking: bool = False) -> str:
    """
    移除模型可能输出的 <think>...</think> 等思考过程，避免前端展示。
    注意：仅做展示层清洗，不改变业务事实。
    """
    import re

    s = (text or "")
    if not show_thinking:
        # 移除 <think>...</think>（含跨行）
        s = re.sub(r"<think>[\s\S]*?</think>", "", s, flags=re.IGNORECASE)
    # 移除多余空行（保留 think 时也做一下清洗）
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _ensure_compliance_and_audit(
    answer_id: str,
    message: str,
    reply_text: str,
    *,
    intent: str,
    slots: dict[str, Any],
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
            {"intent": intent, "slots": slots},
            session_id=session_id,
            user_id=user_id,
            intent=intent,
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
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    knowledge_base_id: str | None = None,
    use_intent_slot: bool = True,
    use_compliance: bool = True,
    use_audit: bool = True,
    progress_callback: Any | None = None,
    stream_callback: Any | None = None,
    show_thinking: bool = False,
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

    async def _progress(stage: str):
        try:
            if callable(progress_callback):
                out = progress_callback(stage)
                if asyncio.iscoroutine(out):
                    await out
        except Exception:
            return

    # 1) 意图与槽位：本版本不再做 intent_slot 抽取（删掉 intent_slot LLM 链路）
    # 先占位，后面由 Coordinator.plan 的 tasks 结构反推 result.intent
    result.intent = "other"
    result.slots = {}
    result.trace["intent"] = result.intent

    # 1.5) Coordinator（方式1）：规划多子任务 → 依次执行 → 融合输出
    await _progress("intent_classifying")
    fund_router = FundAgentRouter()
    ctx_obj = AgentRunContext(
        session_id=session_id,
        user_id=user_id,
        permission_context=permission_context,
        product_ids=product_ids,
        customer_profile=customer_profile,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        knowledge_base_id=knowledge_base_id,
        progress_callback=progress_callback,
        stream_callback=stream_callback,
        show_thinking=bool(show_thinking),
    )
    # 多任务执行时避免“子任务输出 + 最终融合输出”重复拼接：
    # 子任务阶段禁用 token 流式，仅在 final_composing 阶段允许流式输出。
    ctx_no_stream = replace(ctx_obj, stream_callback=None)
    plan = await fund_router.coordinator.plan(message, ctx_obj)
    result.trace["plan"] = {"multi": bool(plan.get("multi")), "tasks": plan.get("tasks") or []}

    # 从 plan 反推 intent（替代已移除的 intent_slot 抽取）
    try:
        p_tasks = plan.get("tasks") or []
        if isinstance(p_tasks, list) and p_tasks:
            t0 = p_tasks[0] if isinstance(p_tasks[0], dict) else {}
            tp = (t0.get("type") or "").strip()
            if tp in ("product_query", "product_interpret", "product_compare"):
                result.intent = tp
            else:
                result.intent = "other"
        else:
            result.intent = "other"
    except Exception:
        result.intent = "other"
    result.slots = dict(result.slots or {})

    # 2) 输入合规
    compliance_input = None
    if use_compliance:
        try:
            await _progress("compliance_input_checking")
            from compliance import check_input
            compliance_input = check_input(message, user_id=user_id)
            if not getattr(compliance_input, "is_allowed", lambda: True)():
                result.answer_blocks = [getattr(compliance_input, "suggestion", None) or "抱歉，该输入未通过合规检查，请修改后重试。"]
                result.compliance = compliance_input.to_dict() if hasattr(compliance_input, "to_dict") else {"action": "reject"}
                if use_audit:
                    _ensure_compliance_and_audit(
                        result.answer_id,
                        message,
                        "",
                        intent=result.intent,
                        slots=result.slots,
                        compliance_input=compliance_input,
                        compliance_output=compliance_input,
                        session_id=session_id,
                        user_id=user_id,
                    )
                return result
        except Exception as e:
            logger.warning("合规输入审查异常: %s", e)

    # 3) 执行 plan（单任务 = 原 5-Agent；多任务 = 多 Agent + 融合）
    tasks = plan.get("tasks") or []
    reply_text = ""
    try:
        await _progress("agent_running")
        if not isinstance(tasks, list) or not tasks:
            # 回退：单任务
            category = fund_router.classifier.classify(message)
            result.trace["intentCategory"] = category
            agent = fund_router.route(category)
            reply_text = await agent.run(message, ctx_obj)
        elif len(tasks) == 1:
            # 单任务：不做 final_composing，直接把业务 agent 的 LLM 输出流式回传
            t0 = tasks[0] if isinstance(tasks[0], dict) else {}
            tp = (t0.get("type") or "").strip()
            q0 = (t0.get("question") or "").strip() or message

            if tp in ("product_query", "product_interpret", "product_compare", "other"):
                agent = fund_router.route(tp)  # type: ignore[arg-type]
                result.trace["intentCategory"] = tp
                reply_text = await agent.run(q0, ctx_obj)
            elif tp == "kb_search":
                # 仅触发知识库（OtherAgent 会根据 ctx.knowledge_base_id 决定是否检索）
                result.trace["intentCategory"] = "other"
                reply_text = await fund_router.other.run(q0, ctx_obj)
            elif tp == "free_answer":
                # free_answer 不触发知识库检索
                result.trace["intentCategory"] = "other"
                ctx_free = replace(ctx_obj, knowledge_base_id=None)
                reply_text = await fund_router.other.run(q0, ctx_free)
            else:
                # 兜底：按 other 处理
                result.trace["intentCategory"] = "other"
                reply_text = await fund_router.other.run(q0, ctx_obj)
        else:
            # 多任务：分别执行，最后融合
            await _progress("multi_task_running")
            parts: list[dict[str, Any]] = []
            for i, t in enumerate(tasks[:4]):  # 限制最多 4 个子任务
                if not isinstance(t, dict):
                    continue
                tp = (t.get("type") or "").strip()
                qx = (t.get("question") or "").strip()
                if not tp or not qx:
                    continue
                await _progress(f"task_{i+1}_{tp}")
                if tp == "kb_search":
                    # 知识库子任务：只允许由 OtherAgent 触发外部知识库检索。
                    # 这样其它业务 Agent（product_query/product_interpret/product_compare）分支不会访问知识库。
                    txt = await fund_router.other.run(qx, ctx_no_stream)
                    parts.append({"type": "kb_search", "question": qx, "text": txt, "items_count": 0})
                elif tp == "free_answer":
                    txt = await fund_router.other._free_answer(qx, ctx_no_stream)  # type: ignore[attr-defined]
                    parts.append({"type": "free_answer", "question": qx, "text": txt})
                else:
                    agent = fund_router.route(tp)  # type: ignore[arg-type]
                    txt = await agent.run(qx, ctx_no_stream)
                    parts.append({"type": tp, "question": qx, "text": txt})

            await _progress("final_composing")
            # 最终融合：用一次 LLM，把多份结果合并成一个自然答案（支持 token 流式）
            from agents.fund_agent_framework import _llm_call_maybe_stream  # type: ignore
            final_inst = (plan.get("final_instruction") or "").strip()
            composer_sys = (
                "你是金融产品问答助手。你将获得多个子任务的结果（文本）。请把它们融合成一份最终答复。"
                "要求："
                "0) 必须按“子任务 question”分别作答，并把每个子任务的 question 作为小标题输出，格式示例："
                "【子问题：...】\\n<回答>\\n\\n【子问题：...】\\n<回答>；"
                "并且必须严格按 tasks 数组中的顺序输出（与用户提问顺序一致）。"
                "1) 只输出一份最终答案，不要再写“我需要分开说明/以下是两个问题/请问你想注册哪个平台/抱歉我无法获取实时数据”等跑题或重复的话；"
                "2) 直接给出可执行结论与步骤；"
                "3) 若某部分来自知识库，请在该部分末尾用一句话标注“依据来自知识库”；"
                "4) 若某子任务内容为空或失败，才说明缺失，禁止编造。"
                "5) 不要使用 markdown（不要用 **、---、# 等）。"
                "重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。"
            )
            composer_user = f"用户原始问题：{message}\n\n融合指令：{final_inst or '请将各子任务结果合并为一个答案。'}\n\n子任务结果(JSON)：\n{json.dumps(parts, ensure_ascii=False)}"
            reply_text = await _llm_call_maybe_stream(
                ctx=ctx_obj,
                messages=[{"role": "system", "content": composer_sys}, {"role": "user", "content": composer_user}],
            )
    except Exception as e:
        # 删除 FAQ 那套路由：不再回退到 AgentScope Router/Toolkit（faq_query/product_list_query 等）
        # 统一回退到 5-Agent 的 OtherAgent（优先外部知识库检索，查不到再自由回答）
        logger.warning("五 Agent 执行异常，回退到 OtherAgent: %s", e, exc_info=True)
        await _progress("agent_fallback_other_running")
        try:
            reply_text = await fund_router.other.run(message, ctx_obj)
        except Exception:
            reply_text = ""
    if not reply_text:
        reply_text = "当前无法生成回复，请稍后重试或换一种方式提问。"
    else:
        reply_text = _strip_think_blocks(reply_text, show_thinking=bool(show_thinking))

    # 4) 输出合规
    compliance_output = None
    if use_compliance:
        try:
            await _progress("compliance_output_checking")
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
            result.answer_id,
            message,
            reply_text,
            intent=result.intent,
            slots=result.slots,
            compliance_input=compliance_input,
            compliance_output=compliance_output or compliance_input,
            session_id=session_id,
            user_id=user_id,
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
