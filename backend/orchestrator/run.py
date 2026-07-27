# -*- coding: utf-8 -*-
"""
编排器主链（T10 #28 原子切换）：原生 AgentScope ReActAgent + Toolkit。

旧手写编排（CoordinatorAgent.plan -> 路由 -> 4 业务 agent -> llm_chat）已在同提交删除
（plan_validation / routing/implicit / fund_agent_framework / 4 业务 agent / llm_chat_stream）。
本文件 ``run_chat_turn_async`` 函数壳保留、内部重写为原生链路：``build_fund_agent``
（T6 ReActAgent + M1-M5 + collector + AuditMiddleware）-> ``ShapeAdapter``（T8 流式保形）
-> ``drive_with_fallback``（T9 栅栏 #3 降级）-> ``collector.build_structured_output``
（栅栏 #5）。对外签名与 ``ChatTurnResult`` 不变（chat 路由零改动）。

6 条栅栏以原生形态落位：
- #1 基金代码可信集：T5 resolve_fund_code + fund_code_registry.is_trusted（臆测代码被拒）。
- #2 M1-M5：T6 assembly（参数校验/白名单/HITL/无效重试/部分失败）。
- #3 启发式兜底：T9 HeuristicFallback（LLM-down/max_iters 降级，栅栏 #1 不放宽）。
- #4 审计：T7 AuditMiddleware（两层 tool_call/reply_outcome，answer_id 经 contextvars 贯穿）。
- #5 structured_outputs：T6 StructuredOutputsCollector（single/compare 形状）。
- #6 流式保形：T8 ShapeAdapter（5 核心阶段/token 分片/推理透传/reset_tools 过滤）。

合规审查（输入/输出）与既有合规审计事件（intent_slot/compliance_input/compliance_output/
reply）保留（不在本次迁移范围）；与 AuditMiddleware 的工具审计事件共存。

测试 seam：``run_chat_turn_async`` 加可选注入参 ``model`` / ``toolkit`` / ``fallback``
（默认 None -> 生产用真组件；测试注入假 ChatModelBase + 桩工具 + 桩兜底，不打真实
LLM/akshare/auth/Redis）。主 seam 验收见 tests/test_run_chat_turn_seam.py（SI-1~12）。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from agentscope.message import Msg, TextBlock
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit

from pkg.logger import get_logger

from agents.native_agent.assembly import build_fund_agent
from agents.native_agent.audit_middleware import (
    reset_audit_answer_id,
    set_audit_answer_id,
)
from agents.native_agent.heuristic_fallback import (
    HeuristicFallback,
    drive_with_fallback,
    heuristic_classify,
)
from agents.native_agent.shape_adapter import ShapeAdapter
from model_gateway.config import GatewayConfig, load_gateway_config
from model_gateway.gateway_model import build_gateway_model

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
    structured_outputs: list[dict[str, Any]] = field(default_factory=list)
    raw_reply: str = ""  # 回复原始文本（ShapeAdapter 已按 show_thinking 过滤），用于持久化


def _resolve_gateway_config(
    base_url: str | None,
    api_key: str | None,
    model_name: str | None,
) -> GatewayConfig | None:
    """按 run_chat_turn_async 收到的模型覆盖参数组装 GatewayConfig。

    chat 路由从 model_id（MySQL 模型管理）读出 base_url/api_key/model_name 覆盖；新链路
    GatewayChatModel 默认读 env，会忽略这些覆盖 -> 回归。本函数在任一覆盖非空时返回
    env 配置 + 覆盖后的 GatewayConfig，供 build_gateway_model 使用；全空时返回 None
    （由 build_fund_agent 走 env 默认）。
    """
    if not (base_url or api_key or model_name):
        return None
    cfg = load_gateway_config()
    if base_url:
        cfg.llm.base_url = base_url
    if api_key:
        cfg.llm.api_key = api_key
    if model_name:
        cfg.llm.model = model_name
    return cfg


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
    """写入合规审计事件（意图、合规输入/输出、回复摘要）；返回 compliance 字段用 dict。

    与 AuditMiddleware 的工具审计事件（tool_call/reply_outcome，经 contextvars 由
    AuditMiddleware 自发）共存：本函数只补合规相关事件，不动工具审计。
    """
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
    # T10 seam 注入（默认 None -> 生产用真组件；测试注入假 model/桩 toolkit/桩 fallback，
    # 不打真实 LLM/akshare/auth/Redis）。对外调用签名向后兼容。
    model: ChatModelBase | None = None,
    toolkit: Toolkit | None = None,
    fallback: HeuristicFallback | None = None,
) -> ChatTurnResult:
    """执行一轮对话编排：原生 ReActAgent 链路 + 合规审查 + 审计落库。

    对外签名与返回 ``ChatTurnResult`` 与切换前一致（chat 路由零改动）。内部从旧
    plan->路由->4 业务 agent 重写为原生 ReActAgent + ShapeAdapter + 启发式兜底。

    Args:
        message: 用户输入。
        model_name / base_url / api_key: 模型覆盖（chat 路由从 model_id 读出）；桥接进
            GatewayConfig 供 GatewayChatModel 使用（不覆盖则走 env）。
        show_thinking: 是否展示模型推理块（透传 ShapeAdapter + GatewayChatModel.enable_thinking）。
        model / toolkit / fallback: T10 seam 注入（测试用，生产省略）。

    Returns:
        ChatTurnResult: answer_blocks、citations、compliance、trace、structured_outputs 等。
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

    # 意图由启发式分类确定（旧路径从 plan 反推；新路径无 plan，用确定性 heuristic_classify
    # 供审计/trace，零 LLM 开销；路由由 agent 自路由承担）。
    result.intent = heuristic_classify(message)
    result.slots = {}
    result.trace["intent"] = result.intent

    async def _progress(stage: str, **kwargs: Any) -> None:
        try:
            if callable(progress_callback):
                out = progress_callback(stage, **kwargs)
                if asyncio.iscoroutine(out):
                    await out
        except Exception:
            return

    # 1) 输入合规（保留，不在迁移范围）
    compliance_input = None
    if use_compliance:
        try:
            await _progress("compliance_checking", message="正在进行合规检查...")
            from compliance import check_input
            compliance_input = check_input(message, user_id=user_id)
            if not getattr(compliance_input, "is_allowed", lambda: True)():
                result.answer_blocks = [
                    getattr(compliance_input, "suggestion", None)
                    or "抱歉，该输入未通过合规检查，请修改后重试。"
                ]
                result.compliance = (
                    compliance_input.to_dict() if hasattr(compliance_input, "to_dict")
                    else {"action": "reject"}
                )
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

    # 2) 装配原生 agent + ShapeAdapter + 启发式兜底（T6/T8/T9）
    gw_config = _resolve_gateway_config(base_url, api_key, model_name)
    agent_model = model
    if agent_model is None and gw_config is not None:
        # 有模型覆盖 -> 用覆盖配置建 GatewayChatModel（stream=True 给 agent）
        agent_model = build_gateway_model(
            stream=True, config=gw_config, enable_thinking=show_thinking
        )
    # agent_model 为 None 时 build_fund_agent 走 env 默认 GatewayChatModel
    agent, collector = build_fund_agent(
        model=agent_model,
        toolkit=toolkit,
        enable_thinking=show_thinking,
        attach_audit=use_audit,
    )

    adapter = ShapeAdapter(
        progress_callback=progress_callback,
        stream_callback=stream_callback,
        show_thinking=show_thinking,
    )
    fb = fallback or HeuristicFallback(
        progress_callback=progress_callback,
        stream_callback=stream_callback,
        show_thinking=show_thinking,
    )

    user_msg = Msg(name="user", content=[TextBlock(text=message)], role="user")

    # 3) answer_id 经 contextvars 贯穿该回合所有审计事件（T7 D2）
    audit_token = set_audit_answer_id(result.answer_id) if use_audit else None
    try:
        await _progress("thinking", message="正在理解您的问题...")
        final_text, fb_result = await drive_with_fallback(adapter, agent, user_msg, fb)
    finally:
        if audit_token is not None:
            reset_audit_answer_id(audit_token)

    # 4) structured_outputs（栅栏 #5）：collector 攥取数 payload -> single/compare 形状。
    #    降级路径（fb_result 非 None）下 collector 可能未攥到 payload，用兜底产出的结构（不放宽）。
    structured: dict[str, Any] | None = None
    try:
        structured = collector.build_structured_output(final_text)
    except Exception as e:
        logger.warning("build_structured_output 异常: %s", e)
    if structured is None and fb_result is not None and fb_result.structured_output:
        structured = fb_result.structured_output
    if structured is not None:
        result.structured_outputs = [structured]

    result.raw_reply = final_text or ""
    reply_text = final_text or "当前无法生成回复，请稍后重试或换一种方式提问。"
    result.trace["degraded_fallback"] = bool(fb_result is not None)
    if fb_result is not None:
        result.trace["fallback_reason"] = fb_result.reason

    # 5) 输出合规（保留，不在迁移范围）
    compliance_output = None
    if use_compliance:
        try:
            await _progress("compliance_final", message="正在进行最终合规检查...")
            from compliance import check_output
            compliance_output = check_output(reply_text, citations=result.citations)
            result.compliance = (
                compliance_output.to_dict() if hasattr(compliance_output, "to_dict") else {}
            )
            if not getattr(compliance_output, "is_allowed", lambda: True)():
                reply_text = (
                    getattr(compliance_output, "suggestion", None)
                    or "回复未通过合规审查，建议转人工确认。"
                )
        except Exception as e:
            logger.warning("合规输出审查异常: %s", e)
            result.compliance = {"action": "pass", "reason": "审查异常降级通过"}
    else:
        result.compliance = {"action": "pass"}
    result.answer_blocks = [reply_text]

    # 6) 合规审计事件（工具审计事件已由 AuditMiddleware 在 3) 经 contextvars 自发）
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
