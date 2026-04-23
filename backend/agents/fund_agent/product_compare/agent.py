from __future__ import annotations

import json
from datetime import datetime
import time
from typing import Any

from agents.fund_agent.runtime import (
    AgentRunContext,
    BaseBusinessAgent,
    _emit_progress,
    _llm_call_maybe_stream,
    _safe_json_loads,
    resolve_agent_skill_keys,
    run_configured_skills,
    resolve_agent_overrides,
)
from pkg.logger import get_logger


logger = get_logger(__name__)


DEFAULT_SYSTEM_PROMPT = """
重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。
重要：若“基金供应商数据”中 payload.ok=true，说明数据已成功获取，禁止回答“系统无法获取数据/技术原因无法获取”等与事实矛盾的话；必须基于数据输出分析。
你的角色定义如下：

# Role: 基金分析专家

## Profile
- language: 中文/英文
- description: 你是中国建设银行的一名拥有多年投资经验的基金分析专家，擅长根据掌握的信息对基金进行对比分析，并给出你的观点。

## Skills
- 对最多5只基金的信息进行分析，包括但不限于基本信息、历史业绩、资产配置等，并从专业的角度对此基金进行对比评价。
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
- 基本信息：基金规模（需要小心迷你基金（规模低于1亿元）的清盘风险）；费率优惠情况；基金经理素质、本基金任职年限、基金经理数量；基金公司情况。
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
- 不同的产品的信息换行输出。

## Workflows
- 接收当日日期。
- 接收获取得到的基金供应商数据。
- 对数据进行解读。
- 综合分析评价基金。
- 输出评价结果。

## Output Format
请参考以下的格式进行输出，注意“{}”内为获取的数据字段或输出说明，其他文字为固定输出版式，在可以获得数据的情况下不需要更改。

参考格式：

【基本信息】  
{需要就基金的基础信息进行汇报，按基金分别介绍基金名称和代码，基金类型，成立时间，基金经理（名字和特点），基金规模，基金个人和机构持有比例，风险等级，当前申赎状态和费率，每个基金不要超过120字，中间不要空行}[在完成所有基金的基本信息展示后，告知最新的报告日期并判断时效性]  
{需要注意数据中的“提示信息”部分，如果有信息，请展示。如有提示基金类型不同，需强调对比意义有限，如果没有提示基金类型不同，则认为类型相同，无须再根据“基金类型”数据判断是否同类。}  

【业绩表现】  
{当获取到此部分数据时才写本部分，如果没有，请明确说明未获取到该部分数据。}[按基金分别介绍在短期（1年及以内）和中长期（1年以上）基金的风险收益特征，此外描述基金盈亏概率和收益分布特点，每个基金不要超过120字，中间不要空行][综合介绍基金的收益相关性]

【行业风格】  
{当获取到此部分数据时才写本部分，如果没有，请明确说明未获取到该部分数据。}[按基金分别介绍晨星风格和行业分布，注意仅给出最高风格暴露的名称，每个基金不要超过100字，中间不要空行]

【资产配置】  
{当获取到此部分数据时才写本部分，如果没有，请明确说明未获取到该部分数据。}[按基金分别介绍大类资产分布和具体的资产（股票、债券、基金）分布特点，如果有股票资产，给出基金持仓估值（P/E、P/B、ROE）数据，每个基金不要超过120字，中间不要空行]

【分析结论】  
{根据你获取到的所有信息，综合对比分析基金情况。当基金类型具有可比性时，选择一只最好的基金并给出理由，同时给出适合的客群和可能的投资方式；当基金类型不具有可比性时，指出以上基金的优势和风险点，并给出适合的客群和可能的投资方式}

【风险提示】  
基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议，不代表财富管理专家的态度和观点。

请你按照要求完成任务。
""".strip()


class ProductCompareAgent(BaseBusinessAgent):
    name = "ProductCompareAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        system_prompt, ctx = resolve_agent_overrides(
            agent_key="product_compare",
            ctx=ctx,
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        )

        if bool(getattr(ctx, "show_thinking", False)):
            system_prompt = system_prompt.replace(
                "重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。",
                "重要：请把推理过程用 <think>...</think> 包裹；最终答案不要包含 <think>。",
            )

        # 1) skills：优先配置；默认 product_compare
        supplier_data: Any = None
        supplier_brief = ""
        skill_keys = resolve_agent_skill_keys(agent_key="product_compare") or ["product_compare"]
        supplier_data = await run_configured_skills(skill_keys=skill_keys, question=question, ctx=ctx)
        payload_obj = supplier_data.get("payload") if isinstance(supplier_data, dict) else None

        # 生成一段短摘要，提升模型“读到数据”的确定性（避免只看见一大坨 JSON）
        try:
            if isinstance(payload_obj, dict) and payload_obj.get("ok") is True and isinstance(payload_obj.get("funds"), list):
                lines: list[str] = []
                for f in payload_obj["funds"][:5]:
                    if not isinstance(f, dict):
                        continue
                    sym = str(f.get("symbol") or "")

                    basic_preview = ""
                    basic = f.get("basic_info")
                    if isinstance(basic, dict) and basic.get("ok") is True and isinstance(basic.get("data"), list):
                        kvs = []
                        for row in basic["data"][:6]:
                            if not isinstance(row, dict):
                                continue
                            k = row.get("item")
                            v = row.get("value")
                            if k is None or v is None:
                                continue
                            kvs.append(f"{k}:{v}")
                        if kvs:
                            basic_preview = "；".join(kvs)

                    perf_preview = ""
                    perf = f.get("performance")
                    if isinstance(perf, dict):
                        ach = perf.get("achievement")
                        if (
                            isinstance(ach, dict)
                            and ach.get("ok") is True
                            and isinstance(ach.get("data"), list)
                            and ach["data"]
                        ):
                            rows = []
                            for r in ach["data"][:3]:
                                if not isinstance(r, dict):
                                    continue
                                # 直接截取前几个字段拼起来（字段名可能随数据源变化）
                                rows.append(" ".join([f"{kk}={r.get(kk)}" for kk in list(r.keys())[:3]]))
                            if rows:
                                perf_preview = "；".join(rows)

                    hold_preview = ""
                    alloc = f.get("asset_allocation")
                    if isinstance(alloc, dict) and alloc.get("ok") is True:
                        data = alloc.get("data")
                        if isinstance(data, dict) and isinstance(data.get("top_holdings"), list) and data["top_holdings"]:
                            names = []
                            for h in data["top_holdings"][:5]:
                                if isinstance(h, dict):
                                    # 优先股票名称字段，否则退化为代码
                                    names.append(str(h.get("股票名称") or h.get("股票代码") or ""))
                            names = [n for n in names if n]
                            if names:
                                hold_preview = "前五持仓:" + "、".join(names)

                    chunks = [x for x in [basic_preview, perf_preview, hold_preview] if x]
                    if chunks:
                        lines.append(f"{sym} | " + " | ".join(chunks))
                if lines:
                    supplier_brief = "\n".join(lines)
        except Exception:
            supplier_brief = ""
        if supplier_data is None and isinstance(ctx.permission_context, dict):
            supplier_data = ctx.permission_context.get("fund_supplier_data") or ctx.permission_context.get("fundData")

        today = datetime.now().strftime("%Y-%m-%d")
        user_prompt = (
            f"当日日期：{today}\n"
            f"用户问题：{(question or '').strip()}\n\n"
            f"基金供应商数据摘要（用于快速阅读，若为空则表示未取到）：\n{supplier_brief or '（空）'}\n\n"
            f"基金供应商数据（JSON，可能为空）：\n{json.dumps(supplier_data, ensure_ascii=False)}"
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
                "[STRUCT_DEBUG][product_compare] llm_done elapsed=%.3fs reply_len=%d",
                time.perf_counter() - t_llm_start,
                len(reply_text or ""),
            )
            try:
                from pkg.fund_formatter import build_compare_output

                t_struct_start = time.perf_counter()
                ctx.structured_outputs = [build_compare_output(supplier_data, reply_text)]
                logger.info(
                    "[STRUCT_DEBUG][product_compare] structured_ready elapsed=%.3fs count=%d",
                    time.perf_counter() - t_struct_start,
                    len(ctx.structured_outputs or []),
                )
            except Exception:
                ctx.structured_outputs = None
            return reply_text
        except Exception as e:
            logger.warning("ProductCompareAgent LLM 调用失败，返回兜底: %s", e)
            return "【产品对比】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。请先提供基金供应商数据或配置数据获取工具。"

