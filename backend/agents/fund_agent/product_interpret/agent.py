from __future__ import annotations

import json
import re
from datetime import datetime
import time
from typing import Any

from agents.fund_agent.runtime import (
    AgentRunContext,
    BaseBusinessAgent,
    _emit_progress,
    _llm_call_maybe_stream,
    resolve_agent_skill_keys,
    run_configured_skills,
    resolve_agent_overrides,
)
from pkg.logger import get_logger


logger = get_logger(__name__)


def _compact_supplier_data_for_prompt(supplier_data: Any) -> Any:
    """压缩供应商数据，避免把大体量时序数据直接塞进 LLM 上下文。"""
    if not isinstance(supplier_data, dict):
        return supplier_data
    out = dict(supplier_data)
    payload = out.get("payload")
    if not isinstance(payload, dict):
        return out
    p2 = dict(payload)
    funds = p2.get("funds")
    if isinstance(funds, list):
        compact_funds: list[dict[str, Any]] = []
        for f in funds[:3]:
            if not isinstance(f, dict):
                continue
            one = dict(f)
            # nav_data / nav_data_periods 数据点太大，仅保留统计信息
            nav = one.get("nav_data")
            if isinstance(nav, dict):
                nrows = len(nav.get("data") or []) if isinstance(nav.get("data"), list) else 0
                one["nav_data"] = {"ok": bool(nav.get("ok")), "rows": nrows}
            navp = one.get("nav_data_periods")
            if isinstance(navp, dict):
                navp_stats: dict[str, Any] = {}
                for k, v in navp.items():
                    if isinstance(v, dict):
                        navp_stats[str(k)] = {
                            "ok": bool(v.get("ok")),
                            "rows": len(v.get("data") or []) if isinstance(v.get("data"), list) else 0,
                        }
                one["nav_data_periods"] = navp_stats
            # 其余模块仅截断前若干行，减少 token
            for mk in (
                "basic_info",
                "achievement",
                "analysis",
                "detail_hold",
                "detail_info",
                "manager_tenure",
                "manager_career",
                "profit_probability",
            ):
                mv = one.get(mk)
                if isinstance(mv, dict) and isinstance(mv.get("data"), list):
                    d = mv.get("data") or []
                    one[mk] = {
                        **mv,
                        "data": d[:30],
                        "total_rows": len(d),
                    }
            compact_funds.append(one)
        p2["funds"] = compact_funds
    out["payload"] = p2
    return out


DEFAULT_SYSTEM_PROMPT = """
重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。
你的角色设定如下：

# Role: 基金分析专家

## Profile
- language: 中文/英文
- description: 你是银行的一名拥有多年投资经验的基金分析专家，擅长根据掌握的信息对基金进行分析，并给出你的观点。

## Skills
- 对单个基金的信息进行分析，包括但不限于基本信息、历史业绩、资产配置等，并从专业的角度对此基金进行评价。
- 以下是不同类型基金一些分析侧重点：

 **货币基金**
- 流动性维度：注意资产配置占比；持有人结构，尽量避免机构持有比例过高的基金（70%）有大额赎回风险。
- 安全性维度：注意基金规模最好在20–500亿区间，过大影响收益弹性，过小有清盘风险。

 **股票/权益基金**
- 行业及风格分析：大中小、价值平衡成长的风格暴露分析；申万一级行业分布分析（是否集中或分散）。
- 资产配置：重仓（股票）资产分析，不建议集中度过高，基金的估值分析。

 **债券基金**
- 资产配置：观察杠杆使用比例（利率风险情况）；信用风险情况。

 **FOF基金**
- 基本信息：尤其注意相关费率，FOF有双重收费问题，费率低更好一些。
- 业绩表现：FOF作为一个大的资产组合，需要更加注重风险调整后收益等指标。
- 资产配置：需要关注子基金的数量和集中度，投资于本公司基金的情况；是否有使用杠杆；资产的流动性等。

 **通用维度**
- 基本信息：基金规模（需要小心迷你基金（货币基金规模低于20亿元，其他类型基金规模低于1亿元）的清盘风险）；费率优惠情况；基金经理素质、本基金任职年限、基金经理数量；基金公司情况。
- 业绩表现：短期（1年及以内）长期（1年以上）的收益；收益稳定性；风险相关指标的综合分析。

## Rules
- 仅对获取的数据进行分析评价，禁止捏造数据。
- 数据中如果包含“报告日期”字段，则为数据最新运算日期或者为基金的公开报告日期（基金的报告日期只有03-31、06-30、09-30和12-31这4种），你需要根据当日日期进行判断数据的时效性。
- 数据中如果包含“大类资产”部分，由于基金在运作中会存在应收应付项目或回购融资等行为（杠杆），会出现各资产总和占净值比例超出100%的情况，请注意。
- 数据中如果包含“行业”部分，你需要结合基金本身进行分析，如果它是一只行业主题型基金，那么行业集中度可以高，在多数情况下，不建议行业集中度过高。
- 输出分析结果时，除非在【分析结论】环节可以进行主观评价外，其他环节仅陈述客观信息。
- 输出分析结果时，请不要使用markdown格式（如，不要使用“**”强调，不要用“#”标题，等等），请使用自然语句。
- 如果获取到的数据包含日期，请在输出时变成“YYYY年MM月DD日”。
- 总体分析评价结果不得超过1800字。
- 请确保输出语言通顺，具有逻辑性。

## Workflows
- 接收当日日期。
- 接收获取到的基金供应商数据。
- 对数据进行解读。
- 综合分析评价基金。
- 输出评价结果。

## Output Format
请参考以下的格式进行输出，注意“{}”内为获取的数据字段或输出说明，其他文字为固定输出版式，在可以获得数据的情况下不需要更改。

参考格式：
【基本信息】

{需要就基金的基础信息进行汇报，按基金分别介绍基金名称和代码，基金类型，成立时间，基金经理（名字和特点），基金规模，基金个人和机构持有比例，风险等级，当前申赎状态和费率，每个基金不要超过120字，中间不要空行}{在完成所有基金的基本信息展示后，告知最新的报告日期并判断时效性}
{需要注意数据中的“提示信息”部分，如果有信息，请展示。}


【业绩表现】

{当获取到此部分数据时才写本部分，如果没有，请明确说明未获取到该部分数据。}{按基金分别介绍在短期（1年及以内）和中长期（1年以上）基金的风险收益特征，此外描述基金盈亏概率和收益分布特点，每个基金不要超过120字，中间不要空行}{综合介绍基金的收益相关性}

【行业风格】

{当获取到此部分数据时才写本部分，如果没有，请明确说明未获取到该部分数据。}{按基金分别介绍晨星风格和行业分布，注意仅给出最高风格暴露的名称，每个基金不要超过100字，中间不要空行}

【资产配置】

{当获取到此部分数据时才写本部分，如果没有，请明确说明未获取到该部分数据。}[按基金分别介绍大类资产分布和具体的资产（股票、债券、基金）分布特点，如果有股票资产，给出基金持仓估值（P/E、P/B、ROE）数据，每个基金不要超过120字，中间不要空行]

【分析结论】

{根据你获取到的所有信息，综合分析基金况。同时给出适合的客群和可能的投资方式}

【风险提示】

基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议，不代表财富管理专家的态度和观点。
""".strip()


class ProductInterpretAgent(BaseBusinessAgent):
    name = "ProductInterpretAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        system_prompt, ctx = resolve_agent_overrides(
            agent_key="product_interpret",
            ctx=ctx,
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        )

        # 展示思考过程：允许模型用 <think>...</think> 包裹推理，并在前端折叠展示
        if bool(getattr(ctx, "show_thinking", False)):
            system_prompt = system_prompt.replace(
                "重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。",
                "重要：请把推理过程用 <think>...</think> 包裹；最终答案不要包含 <think>。",
            )

        # skills：优先配置；默认复用 product_compare
        m = re.search(r"\b\d{6}\b", (question or ""))
        q2 = m.group(0) if m else (question or "")
        skill_keys = resolve_agent_skill_keys(agent_key="product_interpret") or ["product_compare"]
        supplier_data: Any = await run_configured_skills(skill_keys=skill_keys, question=q2, ctx=ctx)
        if supplier_data is None and isinstance(ctx.permission_context, dict):
            supplier_data = ctx.permission_context.get("fund_supplier_data") or ctx.permission_context.get("fundData")

        today = datetime.now().strftime("%Y-%m-%d")
        prompt_supplier_data = _compact_supplier_data_for_prompt(supplier_data)
        user_prompt = (
            f"当日日期：{today}\n"
            f"用户问题：{(question or '').strip()}\n\n"
            f"基金供应商数据（JSON，可能为空）：\n{json.dumps(prompt_supplier_data, ensure_ascii=False)}"
        )
        try:
            t_llm_start = time.perf_counter()
            await _emit_progress(ctx, "llm_generating")
            reply_text = await _llm_call_maybe_stream(
                ctx=ctx,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            logger.info(
                "[STRUCT_DEBUG][product_interpret] llm_done elapsed=%.3fs reply_len=%d",
                time.perf_counter() - t_llm_start,
                len(reply_text or ""),
            )
            try:
                from pkg.fund_formatter import build_single_output

                t_struct_start = time.perf_counter()
                ctx.structured_outputs = [build_single_output(supplier_data, reply_text)]
                logger.info(
                    "[STRUCT_DEBUG][product_interpret] structured_ready elapsed=%.3fs count=%d",
                    time.perf_counter() - t_struct_start,
                    len(ctx.structured_outputs or []),
                )
            except Exception:
                ctx.structured_outputs = None
            return reply_text
        except Exception as e:
            logger.warning("ProductInterpretAgent LLM 调用失败，返回兜底: %s", e)
            return "【产品解析】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。请先提供基金代码或配置数据获取工具。"

