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


def _infer_model_provider(*, base_url: str | None, model_name: str | None) -> str:
    bu = (base_url or "").strip().lower()
    mn = (model_name or "").strip().lower()
    if "dashscope" in bu:
        return "dashscope"
    if "minimax" in bu or "abab" in mn or "minimax" in mn:
        return "minimax"
    if bu:
        return "openai_compatible"
    return "gateway_default"


def _format_multi_task_response(
    parts: list[dict[str, Any]],
    final_instruction: str | None = None,
    *,
    show_thinking: bool = False,
) -> str:
    """
    直接格式化拼接多任务结果，不调用LLM合并。
    
    格式：【子问题：xxx】\n回答内容\n\n【子问题：yyy】\n回答内容

    Args:
        show_thinking: 若为 True，则保留模型 <think>...</think> 推理块，供前端折叠展示。
    """
    if not parts:
        return ""
    
    sections = []
    
    # 如果有最终指令，放在开头
    if final_instruction:
        sections.append(final_instruction.strip())
        sections.append("")
    
    import re
    for part in parts:
        tp = part.get("type", "")
        question = part.get("question", "")
        text = (part.get("text") or "").strip()
        
        if not show_thinking:
            text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        text = text.strip()
        
        # 子问题标题
        if question:
            sections.append(f"【子问题：{question}】")
        
        if text:
            sections.append(text)
        else:
            sections.append("[该部分内容获取失败]")
        
        sections.append("")  # 空行分隔
    
    result = "\n".join(sections)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _build_user_notice(dropped: list[dict[str, Any]]) -> str:
    """ADR-0001 决策 3：部分放行时的模板化用户提示（模板拼接，不调 LLM）。
    在最终答复开头插入，对用户隐藏内部 jargon；被丢弃任务的技术细节由 plan() 落审计。"""
    parts: list[str] = []
    for d in dropped:
        t = d.get("task")
        q = t.get("question") if isinstance(t, dict) else None
        q = (q or "").strip() if isinstance(q, str) else ""
        parts.append(f"「{q or '（无法识别的内容）'}」")
    if not parts:
        return ""
    return "您的问题中，以下部分我暂时无法处理：" + "、".join(parts) + "。您可以换个问法重新提问。"


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
    structured_outputs: list[dict[str, Any]] = field(default_factory=list)
    raw_reply: str = ""  # 剥离 <think> 前的原始文本，用于持久化


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
    # ========== 性能监控：开始计时 ==========
    import time
    t_start = time.perf_counter()
    t_last = t_start
    
    result = ChatTurnResult(
        answer_id=answer_id or uuid.uuid4().hex,
        trace={"traceId": trace_id or uuid.uuid4().hex},
    )
    tid = result.trace.get("traceId", "unknown")
    
    logger.info(f"[PERF][{tid}] 请求开始 | message_len={len(message or '')}")
    
    message = (message or "").strip()
    if not message:
        result.answer_blocks = [""]
        result.compliance = {"action": "pass", "reason": "空输入"}
        return result

    async def _progress(stage: str, **kwargs):
        """发送进度事件，支持额外参数"""
        try:
            if callable(progress_callback):
                out = progress_callback(stage, **kwargs)
                if asyncio.iscoroutine(out):
                    await out
        except Exception:
            return

    first_stream_token_seen = False

    async def _stream_with_ttft(token_text: str):
        nonlocal first_stream_token_seen
        if token_text and (not first_stream_token_seen):
            first_stream_token_seen = True
            await _progress("model_first_token")
        try:
            if callable(stream_callback):
                out = stream_callback(token_text)
                if asyncio.iscoroutine(out):
                    await out
        except Exception:
            return

    # 1) 意图与槽位：本版本不再做 intent_slot 抽取（删掉 intent_slot LLM 链路）
    # 先占位，后面由 Coordinator.plan 的 tasks 结构反推 result.intent
    result.intent = "other"
    result.slots = {}
    result.trace["intent"] = result.intent
    
    # ========== 性能监控：初始化完成 ==========
    t_now = time.perf_counter()
    logger.info(f"[PERF][{tid}] 初始化完成 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
    t_last = t_now

    # 1.5) Coordinator（方式1）：规划多子任务 → 依次执行 → 融合输出
    await _progress("thinking", message="正在理解您的问题...")
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
        stream_callback=_stream_with_ttft if callable(stream_callback) else None,
        show_thinking=bool(show_thinking),
        answer_id=result.answer_id,  # ADR-0001 决策 5：供 CoordinatorAgent.plan 落 plan 校验审计事件
    )
    # 多任务执行时避免“子任务输出 + 最终融合输出”重复拼接：
    # 子任务阶段禁用 token 流式，仅在 final_composing 阶段允许流式输出。
    ctx_no_stream = replace(ctx_obj, stream_callback=None)
    
    # ========== 性能监控：开始规划 ==========
    t_now = time.perf_counter()
    logger.info(f"[PERF][{tid}] 开始任务规划 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
    t_last = t_now
    await _progress("planning_start")
    plan = await fund_router.coordinator.plan(message, ctx_obj)
    await _progress("planning_end", tasks_count=len(plan.get("tasks") or []))
    result.trace["plan"] = {"multi": bool(plan.get("multi")), "tasks": plan.get("tasks") or []}
    
    # ========== 性能监控：规划完成 ==========
    t_now = time.perf_counter()
    logger.info(f"[PERF][{tid}] 任务规划完成 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s | tasks={len(plan.get('tasks') or [])}")
    t_last = t_now
    
    # 发送规划完成进度
    tasks_count = len(plan.get("tasks") or [])
    if tasks_count > 1:
        await _progress("planning_done", message=f"已拆分为 {tasks_count} 个子任务，正在处理...")
    else:
        await _progress("planning_done", message="正在查询相关信息...")
    
    if isinstance(plan.get("abort"), dict):
        abort_obj = plan.get("abort") or {}
        abort_msg = (abort_obj.get("message") or "").strip() or "未查询到基金代码，请补充准确的基金名称或直接提供6位基金代码。"
        result.answer_blocks = [abort_msg]
        result.compliance = {"action": "pass", "reason": str(abort_obj.get("reason") or "planner_abort")}
        result.trace["plan_abort"] = abort_obj
        return result

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
            await _progress("compliance_checking", message="正在进行合规检查...")
            await _progress("compliance_start")
            
            # ========== 性能监控：开始输入合规 ==========
            t_now = time.perf_counter()
            logger.info(f"[PERF][{tid}] 开始输入合规检查 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
            t_last = t_now
            
            from compliance import check_input
            compliance_input = check_input(message, user_id=user_id)
            await _progress("compliance_end", allowed=bool(getattr(compliance_input, "is_allowed", lambda: True)()))
            
            # ========== 性能监控：输入合规完成 ==========
            t_now = time.perf_counter()
            logger.info(f"[PERF][{tid}] 输入合规检查完成 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
            t_last = t_now
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
        await _progress("agent_prepare_start", tasks_count=len(tasks) if isinstance(tasks, list) else 0)
        
        # ========== 性能监控：开始 Agent 执行 ==========
        t_now = time.perf_counter()
        logger.info(f"[PERF][{tid}] 开始 Agent 执行 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
        t_last = t_now
        
        await _progress("generating", message="正在生成回答...")
        
        if not isinstance(tasks, list) or not tasks:
            # 回退：单任务
            category = fund_router.classifier.classify(message)
            result.trace["intentCategory"] = category
            agent = fund_router.route(category)
            provider = _infer_model_provider(base_url=ctx_obj.base_url, model_name=ctx_obj.model_name)
            await _progress("agent_prepare_end", intent=category)
            await _progress(
                "model_request_ready",
                model_name=ctx_obj.model_name or "",
                provider=provider,
                route="agent_runtime_stream" if callable(ctx_obj.stream_callback) and bool(ctx_obj.model_name) else "agent_runtime_non_stream",
                prompt_chars_proxy=len(message or ""),
                prompt_messages_proxy=1,
                retry_count=-1,
            )
            await _progress("retrieval_start")
            await _progress("model_request_start")
            reply_text = await agent.run(message, ctx_obj)
            await _progress("retrieval_end")
        elif len(tasks) == 1:
            # 单任务：不做 final_composing，直接把业务 agent 的 LLM 输出流式回传
            t0 = tasks[0] if isinstance(tasks[0], dict) else {}
            tp = (t0.get("type") or "").strip()
            q0 = (t0.get("question") or "").strip() or message

            # 兼容旧规划类型：kb_search/free_answer 统一映射到 other
            if tp in ("kb_search", "free_answer"):
                tp = "other"

            if tp in ("product_query", "product_interpret", "product_compare", "other"):
                agent = fund_router.route(tp)  # type: ignore[arg-type]
                result.trace["intentCategory"] = tp
                provider = _infer_model_provider(base_url=ctx_obj.base_url, model_name=ctx_obj.model_name)
                await _progress("agent_prepare_end", intent=tp)
                await _progress(
                    "model_request_ready",
                    model_name=ctx_obj.model_name or "",
                    provider=provider,
                    route="agent_runtime_stream" if callable(ctx_obj.stream_callback) and bool(ctx_obj.model_name) else "agent_runtime_non_stream",
                    prompt_chars_proxy=len(q0 or ""),
                    prompt_messages_proxy=1,
                    retry_count=-1,
                )
                await _progress("retrieval_start")
                await _progress("model_request_start")
                reply_text = await agent.run(q0, ctx_obj)
                await _progress("retrieval_end")
            else:
                # 兜底：按 other 处理
                result.trace["intentCategory"] = "other"
                provider = _infer_model_provider(base_url=ctx_obj.base_url, model_name=ctx_obj.model_name)
                await _progress("agent_prepare_end", intent="other")
                await _progress(
                    "model_request_ready",
                    model_name=ctx_obj.model_name or "",
                    provider=provider,
                    route="agent_runtime_stream" if callable(ctx_obj.stream_callback) and bool(ctx_obj.model_name) else "agent_runtime_non_stream",
                    prompt_chars_proxy=len(q0 or ""),
                    prompt_messages_proxy=1,
                    retry_count=-1,
                )
                await _progress("retrieval_start")
                await _progress("model_request_start")
                reply_text = await fund_router.other.run(q0, ctx_obj)
                await _progress("retrieval_end")
        else:
            # 多任务：并行执行，直接格式化拼接（不调用LLM合并）
            await _progress("multi_task_running", message=f"正在并行处理 {len(tasks)} 个子任务...")

            # 定义单任务执行函数
            async def run_single_task(t: dict, idx: int) -> dict[str, Any] | None:
                if not isinstance(t, dict):
                    return None
                tp = (t.get("type") or "").strip()
                qx = (t.get("question") or "").strip()
                if not tp or not qx:
                    return None
                
                # 友好的任务类型名称
                task_names = {
                    "product_query": "产品查询",
                    "product_interpret": "产品解读",
                    "product_compare": "产品对比",
                    "other": "信息检索"
                }
                task_name = task_names.get(tp, tp)
                await _progress(f"task_{idx+1}", message=f"正在执行：{task_name}...")
                try:
                    if tp in ("kb_search", "free_answer"):
                        tp = "other"
                    agent = fund_router.route(tp)  # type: ignore[arg-type]
                    txt = await agent.run(qx, ctx_no_stream)
                    return {"type": tp, "question": qx, "text": txt}
                except Exception as e:
                    logger.warning(f"任务 {idx+1} 执行失败: {e}")
                    return {"type": tp, "question": qx, "text": f"[执行失败: {str(e)}]"}

            # 并行执行所有任务
            tasks_to_run = [t for t in tasks[:4] if isinstance(t, dict)]
            results = await asyncio.gather(*[
                run_single_task(t, i) for i, t in enumerate(tasks_to_run)
            ])

            # 过滤有效结果，保持顺序
            parts = [r for r in results if r is not None]

            await _progress("final_composing", message="正在整合结果...")
            # 直接格式化拼接，不调用LLM合并
            final_inst = (plan.get("final_instruction") or "").strip()
            await _progress("agent_prepare_end", intent="multi_task")
            await _progress(
                "model_request_ready",
                model_name=ctx_obj.model_name or "",
                provider=_infer_model_provider(base_url=ctx_obj.base_url, model_name=ctx_obj.model_name),
                route="local_merge_no_llm",
                prompt_chars_proxy=sum(len(str((p or {}).get("text") or "")) for p in parts),
                prompt_messages_proxy=len(parts),
                retry_count=-1,
            )
            reply_text = _format_multi_task_response(parts, final_inst, show_thinking=bool(show_thinking))

        # 删除 FAQ 那套路由：不再回退到 AgentScope Router/Toolkit（faq_query/product_list_query 等）
        # 统一回退到 5-Agent 的 OtherAgent（优先外部知识库检索，查不到再自由回答）
    except Exception as e:   
        logger.warning("五 Agent 执行异常，回退到 OtherAgent: %s", e, exc_info=True)
        await _progress("agent_fallback_other_running")
        try:
            reply_text = await fund_router.other.run(message, ctx_obj)
        except Exception:
            reply_text = ""
    
    # ========== 性能监控：Agent 执行完成 ==========
    t_now = time.perf_counter()
    logger.info(f"[PERF][{tid}] Agent 执行完成 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s | reply_len={len(reply_text)}")
    t_last = t_now
    
    if not reply_text:
        reply_text = "当前无法生成回复，请稍后重试或换一种方式提问。"
    else:
        result.raw_reply = reply_text  # 保存剥离前的原始文本（含 <think>）
        reply_text = _strip_think_blocks(reply_text, show_thinking=bool(show_thinking))

    # ADR-0001 决策 3：部分放行时在最终答复开头插入模板化用户提示（模板拼接，不调 LLM）。
    # 覆盖单任务与多任务：partial_pass 可能只保留 1 个任务（走单任务分支），仍需提示被丢弃的部分。
    dropped_tasks = plan.get("dropped") if isinstance(plan, dict) else None
    if dropped_tasks:
        notice = _build_user_notice(dropped_tasks)
        if notice:
            reply_text = (notice + "\n\n" + reply_text) if reply_text else notice

    # 结构化输出：由业务 agent 写入 ctx_obj.structured_outputs，这里统一透传给 API（SSE done / 非流式 JSON）
    try:
        so = getattr(ctx_obj, "structured_outputs", None)
        if isinstance(so, list) and so:
            result.structured_outputs = [x for x in so if isinstance(x, dict)]
    except Exception:
        pass

    # 4) 输出合规
    compliance_output = None
    if use_compliance:
        try:
            await _progress("compliance_final", message="正在进行最终合规检查...")
            
            # ========== 性能监控：开始输出合规 ==========
            t_now = time.perf_counter()
            logger.info(f"[PERF][{tid}] 开始输出合规检查 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
            t_last = t_now
            
            from compliance import check_output
            compliance_output = check_output(reply_text, citations=result.citations)
            
            # ========== 性能监控：输出合规完成 ==========
            t_now = time.perf_counter()
            logger.info(f"[PERF][{tid}] 输出合规检查完成 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
            t_last = t_now
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
        # ========== 性能监控：开始审计 ==========
        t_now = time.perf_counter()
        logger.info(f"[PERF][{tid}] 开始审计落库 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
        t_last = t_now
        
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
        
        # ========== 性能监控：审计完成 ==========
        t_now = time.perf_counter()
        logger.info(f"[PERF][{tid}] 审计落库完成 | 耗时={t_now - t_last:.3f}s | 累计={t_now - t_start:.3f}s")
        t_last = t_now
    
    # ========== 性能监控：请求结束 ==========
    t_now = time.perf_counter()
    logger.info(f"[PERF][{tid}] 请求结束 | 总耗时={t_now - t_start:.3f}s")
    
    # ========== 打印性能监控摘要 ==========
    try:
        from pkg.metrics import get_metrics_collector
        metrics_collector = get_metrics_collector()
        metrics_collector.print_summary()
        
        # 识别最慢模块
        slowest = metrics_collector.get_slowest_module()
        if slowest:
            logger.warning(f"[PERF][{tid}] ⚠️  性能瓶颈: {slowest}")
    except Exception as e:
        logger.warning(f"打印性能摘要失败: {e}")

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
