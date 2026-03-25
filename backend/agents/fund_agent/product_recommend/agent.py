from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from agents.fund_agent.runtime import (
    AgentRunContext,
    BaseBusinessAgent,
    _emit_progress,
    _llm_call_maybe_stream,
    resolve_agent_overrides,
    resolve_agent_skill_keys,
    run_configured_skills,
)
from pkg.logger import get_logger


logger = get_logger(__name__)


DEFAULT_SYSTEM_PROMPT = """
重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。
你是银行基金投顾助手，需要基于“客户画像”和“候选产品数据”给出产品推荐。

规则：
1) 仅基于输入数据做推荐，禁止编造不存在的产品信息或业绩数据。
2) 推荐数量必须严格等于用户指定数量（recommend_count）；若无明确指定，按传入默认值执行。
3) 若可推荐产品不足，也要明确说明不足原因，并尽可能给出可推荐项。
4) 每个推荐产品都要给出“推荐原因”，原因需关联客户画像中的风险偏好、期限、收益诉求、流动性偏好等维度。
5) 输出语言自然、专业、简洁，不使用 markdown 标题/加粗符号。
6) 最后必须追加风险提示：基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议。

输出格式（纯文本）：
推荐结果（共N只）：
1. 产品名称（产品代码）
推荐原因：...
适配标签：...

2. ...
""".strip()


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _resolve_recommend_count(question: str, permission_context: dict[str, Any] | None) -> int:
    """
    推荐数量规则：
    - 最小 1，最大 10
    - 优先读取 permission_context 中的显式参数
    - 其次尝试从问题中解析 topN/N只/推荐N个
    - 默认 3
    """
    default_count = 3
    count = default_count
    ctx = permission_context if isinstance(permission_context, dict) else {}

    for key in ("recommend_count", "count", "top_k", "topK", "top"):
        if key in ctx:
            count = _safe_int(ctx.get(key), default_count)
            break

    q = (question or "").strip()
    if not any(k in ctx for k in ("recommend_count", "count", "top_k", "topK", "top")) and q:
        patterns = [
            r"目标推荐数量[^0-9]*(\d{1,2})",
            r"(?:top|TOP)\s*(\d{1,2})",
            r"推荐\s*(\d{1,2})\s*[个只款]",
            r"(\d{1,2})\s*[个只款]\s*(?:基金|产品)",
            r"(?:前|要|给我)\s*(\d{1,2})\s*(?:只|个)",
        ]
        for p in patterns:
            m = re.search(p, q)
            if m:
                count = _safe_int(m.group(1), default_count)
                break

    return max(1, min(10, count))


def _resolve_customer_profile(question: str, permission_context: dict[str, Any] | None, ctx: AgentRunContext) -> str:
    profile = (ctx.customer_profile or "").strip()
    if profile:
        return profile
    pc = permission_context if isinstance(permission_context, dict) else {}
    profile = str(pc.get("customer_profile") or pc.get("customerProfile") or "").strip()
    if profile:
        return profile
    return (question or "").strip()


class ProductRecommendAgent(BaseBusinessAgent):
    name = "ProductRecommendAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        system_prompt, ctx = resolve_agent_overrides(
            agent_key="product_recommend",
            ctx=ctx,
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        )

        if bool(getattr(ctx, "show_thinking", False)):
            system_prompt = system_prompt.replace(
                "重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。",
                "重要：请把推理过程用 <think>...</think> 包裹；最终答案不要包含 <think>。",
            )

        recommend_count = _resolve_recommend_count(question=question, permission_context=ctx.permission_context)
        customer_profile = _resolve_customer_profile(question=question, permission_context=ctx.permission_context, ctx=ctx)

        # 传给 skill 的 question 需要包含客户画像与目标数量，便于数据取数与筛选。
        skill_question = (
            f"用户问题：{(question or '').strip()}\n"
            f"客户画像：{customer_profile or '（未提供）'}\n"
            f"目标推荐数量（必须严格输出该数量，范围1~10）：{recommend_count}"
        )

        skill_keys = resolve_agent_skill_keys(agent_key="product_recommend") or ["product_recommend"]
        supplier_data: Any = await run_configured_skills(skill_keys=skill_keys, question=skill_question, ctx=ctx)
        if supplier_data is None and isinstance(ctx.permission_context, dict):
            supplier_data = (
                ctx.permission_context.get("fund_supplier_data")
                or ctx.permission_context.get("fundData")
                or ctx.permission_context.get("products")
                or ctx.permission_context.get("candidate_products")
            )

        today = datetime.now().strftime("%Y-%m-%d")
        user_prompt = (
            f"当日日期：{today}\n"
            f"用户问题：{(question or '').strip()}\n"
            f"客户画像：{customer_profile or '（未提供）'}\n"
            f"目标推荐数量（必须严格输出该数量，范围1~10）：{recommend_count}\n\n"
            f"候选产品数据（JSON，可能为空）：\n{json.dumps(supplier_data, ensure_ascii=False)}"
        )

        try:
            await _emit_progress(ctx, "llm_generating")
            return await _llm_call_maybe_stream(
                ctx=ctx,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            logger.warning("ProductRecommendAgent LLM 调用失败，返回兜底: %s", e)
            return (
                "【产品推荐】当前无法完成推荐，请稍后重试。"
                f"建议推荐数量：{recommend_count}（范围 1-10，默认 3）。"
            )
