# -*- coding: utf-8 -*-
"""
五 Agent 框架（先搭骨架，后续再填提示词/工具调用）：

- IntentClassifierAgent：将用户问题分类为四大类
  - product_query（产品查询）
  - product_interpret（产品解析）
  - product_compare（产品对比）
  - other（其它）
- 四个业务 Agent：分别处理四大类

当前版本仅提供“可运行框架 + 稳定兜底”，不实现具体工具调用。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Literal

from pkg.logger import get_logger

logger = get_logger(__name__)

IntentCategory = Literal["product_query", "product_interpret", "product_compare", "other"]

def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return s


def _heuristic_classify(text: str) -> IntentCategory:
    """轻量启发式分类：保证在 LLM 不可用时也能工作。"""
    t = (text or "").strip()
    if not t:
        return "other"
    low = t.lower()
    # 提取 6 位基金代码数量（用于判断“对比/解析”场景）
    import re

    codes = re.findall(r"(?<!\d)\d{6}(?!\d)", t)
    uniq_codes = list(dict.fromkeys(codes))

    # 产品对比：显式“对比/比较”或出现多只基金代码
    if any(k in t for k in ("对比", "比较", "哪个好", "差异", "PK", "pk")) or len(uniq_codes) >= 2:
        return "product_compare"

    # 产品查询：榜单/筛选/推荐/“哪些”类问题（常见：近期收益高、风险低）
    query_triggers = (
        "有哪些",
        "哪些",
        "推荐",
        "排行",
        "排名",
        "榜",
        "top",
        "TOP",
        "筛选",
        "找",
        "选",
        "收益率高",
        "涨幅",
        "近期",
        "最近",
        "近一周",
        "近1周",
        "近一月",
        "近1月",
        "近三月",
        "近3月",
        "近半年",
        "近6月",
        "近一年",
        "近1年",
        "今年来",
        "成立来",
        "稳健",
        "低风险",
    )
    if any(k in t for k in query_triggers):
        # 若是“单只基金解析”更像 interpret（见下方）
        if len(uniq_codes) == 0:
            return "product_query"

    # 产品解析：单只基金/产品“怎么样/分析/解读/适不适合/风险点”
    interpret_triggers = ("解析", "解读", "分析", "怎么样", "怎么看", "要点", "风险", "适合", "条款", "能买吗", "值不值得")
    if any(k in t for k in interpret_triggers) or (len(uniq_codes) == 1 and any(k in t for k in ("风险", "收益", "回撤", "波动", "稳健"))):
        return "product_interpret"

    # 兜底：包含“基金/理财/产品”关键词但未命中时，优先认为是产品查询
    if any(k in t for k in ("基金", "理财", "产品", "收益率", "净值")):
        return "product_query"
    # fallback
    if "compare" in low:
        return "product_compare"
    if "list" in low or "search" in low:
        return "product_query"
    return "other"


def _parse_classifier_output(s: str) -> IntentCategory | None:
    """解析分类器输出（预期为 JSON），容错处理。"""
    if not s:
        return None
    s = s.strip()
    # 允许模型直接输出类别字符串
    if s in ("product_query", "product_interpret", "product_compare", "other"):
        return s  # type: ignore[return-value]
    try:
        obj = json.loads(s)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    cat = (obj.get("category") or obj.get("intent") or obj.get("type") or "").strip()
    if cat in ("product_query", "product_interpret", "product_compare", "other"):
        return cat  # type: ignore[return-value]
    # 允许中文
    mapping = {
        "产品查询": "product_query",
        "产品解析": "product_interpret",
        "产品对比": "product_compare",
        "其它": "other",
        "其他": "other",
    }
    if cat in mapping:
        return mapping[cat]  # type: ignore[return-value]
    return None


@dataclass
class AgentRunContext:
    """运行上下文（后续可扩展：用户、权限、会话、产品池等）。"""

    session_id: str | None = None
    user_id: str | None = None
    permission_context: dict[str, Any] | None = None
    product_ids: list[str] | None = None
    customer_profile: str | None = None

    # 模型覆盖（来自 model_id 的 ai_models 配置）
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None

    # 其它 Agent 走知识库检索时使用
    knowledge_base_id: str | None = None

    # SSE/流式体验优化：进度与 token 回调（由 API 层注入；Agent 可选使用）
    progress_callback: Any | None = None
    stream_callback: Any | None = None


async def _emit_progress(ctx: AgentRunContext, stage: str):
    try:
        cb = getattr(ctx, "progress_callback", None)
        if callable(cb):
            out = cb(stage)
            if asyncio.iscoroutine(out):
                await out
    except Exception:
        return


async def _llm_call_maybe_stream(
    *,
    ctx: AgentRunContext,
    messages: list[dict[str, str]],
) -> str:
    """
    统一的 LLM 调用：
    - 若 API 层提供了 stream_callback 且当前轮模型配置有 base_url：走 OpenAI 兼容流式，边生成边推送 token
    - 否则：走原 llm_chat（一次性返回）
    """
    stream_cb = getattr(ctx, "stream_callback", None)
    if callable(stream_cb) and (ctx.base_url or "").strip() and (ctx.model_name or "").strip():
        try:
            from model_gateway.llm import llm_chat_stream

            full = ""
            async for t in llm_chat_stream(
                messages,
                model=ctx.model_name,
                base_url=ctx.base_url,
                api_key=ctx.api_key,
            ):
                if not t:
                    continue
                full += t
                out = stream_cb(t)
                if asyncio.iscoroutine(out):
                    await out
            return full.strip()
        except Exception as e:
            logger.warning("流式 LLM 调用失败，回退到非流式: %s", e)
            # fallthrough to non-stream

    from model_gateway.llm import llm_chat

    return (await asyncio.to_thread(llm_chat, messages, model=ctx.model_name, base_url=ctx.base_url, api_key=ctx.api_key)).strip()


class IntentClassifierAgent:
    """
    意图识别 Agent（框架版）。

    当前策略：
    - 先启发式分类（确保稳定）
    - 若后续你提供提示词/工具调用，可改为强制走 LLM 分类并输出 JSON
    """

    def classify(self, question: str) -> IntentCategory:
        return _heuristic_classify(question)


class BaseBusinessAgent:
    name: str = "BaseBusinessAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        raise NotImplementedError


class ProductQueryAgent(BaseBusinessAgent):
    name = "ProductQueryAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        system_prompt = """
重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。
你的角色设定如下：

# Role: 基金分析专家

## Profile
- language: 中文/英文
- description: 你是银行的一名拥有多年投资经验的基金分析专家，擅长根据掌握的信息对基金进行分析，并给出你的观点。

## Skills
- 对单个或多个基金的信息进行简单分析，主要列出数据项包括但不限于基本信息、历史业绩、资产配置等，并从专业的角度对此基金进行评价。
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

【分析结论】

{根据你获取到的所有信息，综合分析基金况。同时给出适合的客群和可能的投资方式}

【风险提示】

基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议，不代表财富管理专家的态度和观点。

请你按照要求完成任务。
""".strip()

        # 产品查询 skill：
        # - 有基金代码：聚合单/多基金数据
        # - 无基金代码：走榜单/筛选 TopN（用于“近期收益高、风险低”等查询）
        supplier_data: Any = None
        try:
            await _emit_progress(ctx, "skill_fetching")
            from agents.skills.product_query.runtime import run as run_skill  # type: ignore

            skill_json_str = await run_skill(question, {"session_id": ctx.session_id, "user_id": ctx.user_id})
            supplier_data = {"skill": "fund-analysis", "payload": _safe_json_loads(skill_json_str)}
        except Exception:
            # 兜底：历史版本只实现了 product_compare skill
            try:
                await _emit_progress(ctx, "skill_fetching")
                from agents.skills.product_compare.runtime import run as run_compare_skill  # type: ignore

                skill_json_str = await run_compare_skill(question, {"session_id": ctx.session_id, "user_id": ctx.user_id})
                supplier_data = {"skill": "fund-analysis", "payload": _safe_json_loads(skill_json_str)}
            except Exception:
                supplier_data = None
        if supplier_data is None and isinstance(ctx.permission_context, dict):
            supplier_data = ctx.permission_context.get("fund_supplier_data") or ctx.permission_context.get("fundData")

        today = datetime.now().strftime("%Y-%m-%d")
        user_prompt = (
            f"当日日期：{today}\n"
            f"用户问题：{(question or '').strip()}\n\n"
            f"基金供应商数据（JSON，可能为空）：\n{json.dumps(supplier_data, ensure_ascii=False)}"
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
            logger.warning("ProductQueryAgent LLM 调用失败，返回兜底: %s", e)
            return "【产品查询】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出结果。请先提供基金代码或配置数据获取工具。"


class ProductInterpretAgent(BaseBusinessAgent):
    name = "ProductInterpretAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        system_prompt = """
重要：不要输出任何 <think> 或推理过程，只输出最终结果文本。
你的角色设定如下：

# Role: 基金分析专家

## Profile
- language: 中文/英文
- description: 你是中国建设银行的一名拥有多年投资经验的基金分析专家，擅长根据掌握的信息对基金进行分析，并给出你的观点。

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

请你按照要求完成任务。
""".strip()

        # 复用产品对比 skill（AkShare 聚合数据）。产品解析仅分析单只基金：只取第一个 6 位代码。
        supplier_data: Any = None
        try:
            import re
            from agents.skills.product_compare.runtime import run as run_skill  # type: ignore

            await _emit_progress(ctx, "skill_fetching")
            m = re.search(r"\b\d{6}\b", (question or ""))
            q2 = m.group(0) if m else (question or "")
            skill_json_str = await run_skill(q2, {"session_id": ctx.session_id, "user_id": ctx.user_id})
            supplier_data = {"skill": "fund-analysis", "payload": _safe_json_loads(skill_json_str)}
        except Exception:
            supplier_data = None
        if supplier_data is None and isinstance(ctx.permission_context, dict):
            supplier_data = ctx.permission_context.get("fund_supplier_data") or ctx.permission_context.get("fundData")

        today = datetime.now().strftime("%Y-%m-%d")
        user_prompt = (
            f"当日日期：{today}\n"
            f"用户问题：{(question or '').strip()}\n\n"
            f"基金供应商数据（JSON，可能为空）：\n{json.dumps(supplier_data, ensure_ascii=False)}"
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
            logger.warning("ProductInterpretAgent LLM 调用失败，返回兜底: %s", e)
            return "【产品解析】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。请先提供基金代码或配置数据获取工具。"


class ProductCompareAgent(BaseBusinessAgent):
    name = "ProductCompareAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        system_prompt = """
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

        # 1) 优先走 skill 拉取对比所需数据（AkShare）；失败则回退到上游传入的 supplier_data
        supplier_data: Any = None
        supplier_brief = ""
        try:
            from agents.skills.product_compare.runtime import run as run_skill  # type: ignore

            skill_json_str = await run_skill(question, {"session_id": ctx.session_id, "user_id": ctx.user_id})
            payload_obj = _safe_json_loads(skill_json_str)
            supplier_data = {"skill": "fund-analysis", "payload": payload_obj}

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
                            if isinstance(ach, dict) and ach.get("ok") is True and isinstance(ach.get("data"), list) and ach["data"]:
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
        except Exception as e:
            supplier_data = None
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
            await _emit_progress(ctx, "llm_generating")
            return await _llm_call_maybe_stream(
                ctx=ctx,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            logger.warning("ProductCompareAgent LLM 调用失败，返回兜底: %s", e)
            return "【产品对比】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。请先提供基金供应商数据或配置数据获取工具。"


class OtherAgent(BaseBusinessAgent):
    name = "OtherAgent"

    async def run(self, question: str, ctx: AgentRunContext) -> str:
        q = (question or "").strip()
        if not q:
            return ""

        kb_id = (ctx.knowledge_base_id or "").strip()
        # 若用户未选择知识库，则直接自由回答
        if not kb_id:
            return await self._free_answer(q, ctx)

        items = await self._external_kb_search(q, kb_id, top_k=5)
        if items:
            return await self._answer_with_kb(q, items, ctx)
        # 知识库检索不到，则模型自由回答
        return await self._free_answer(q, ctx, hint="知识库未检索到相关依据")

    async def _external_kb_search(self, question: str, knowledge_base_id: str, top_k: int) -> list[dict[str, Any]]:
        base_url = (os.getenv("EXTERNAL_KB_BASE_URL") or "").strip()
        api_key = (os.getenv("EXTERNAL_KB_API_KEY") or "").strip()
        if not base_url:
            return []
        try:
            import httpx
        except ImportError:
            return []
        url = f"{base_url.rstrip('/')}/api/v1/knowledge-search"
        payload: dict[str, Any] = {
            "query": (question or "").strip(),
            "knowledge_base_ids": [knowledge_base_id] if (knowledge_base_id or "").strip() else [],
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OtherAgent external kb search failed: %s", e)
            return []

        raw_items: Any = None
        if isinstance(data, dict):
            raw_items = data.get("items")
            if raw_items is None:
                raw_items = data.get("data")
            if raw_items is None:
                raw_items = data.get("list")
            if raw_items is None:
                raw_items = data.get("results")
        else:
            raw_items = data

        normalized: list[dict[str, Any]] = []
        if isinstance(raw_items, list):
            for it in raw_items[: max(1, int(top_k or 5))]:
                if not isinstance(it, dict):
                    continue
                title = (it.get("knowledge_title") or it.get("knowledge_filename") or it.get("title") or "").strip()
                content = it.get("content") or it.get("matched_content") or ""
                snippet = it.get("matched_content") or it.get("content") or ""
                normalized.append(
                    {
                        "title": title or "未命名片段",
                        "content": content,
                        "snippet": snippet,
                        "score": it.get("score"),
                        "source": (it.get("knowledge_filename") or it.get("knowledge_title") or it.get("source") or "").strip(),
                    }
                )
        return normalized

    async def _answer_with_kb(self, question: str, items: list[dict[str, Any]], ctx: AgentRunContext) -> str:
        context_blocks: list[str] = []
        for i, it in enumerate(items, start=1):
            c = (it.get("content") or "").strip()
            if not c:
                continue
            title = it.get("title") or it.get("source") or f"片段{i}"
            score = it.get("score")
            context_blocks.append(f"[{i}] {title} (score={score})\n{c}")
        context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else ""
        sys_prompt = (
            "你是知识库问答助手。请严格基于给定的【知识库片段】回答用户问题；"
            "若片段中找不到依据，请明确说明“知识库未检索到相关依据”，并给出建议的补充提问方向。"
            "回答要简洁、结构化，可用要点列表。"
        )
        user_content = f"用户问题：{question}\n\n【知识库片段】\n{context_text or '（无）'}"
        return await self._llm_call(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}],
            ctx,
        )

    async def _free_answer(self, question: str, ctx: AgentRunContext, hint: str | None = None) -> str:
        sys_prompt = "你是一个通用助手，请用中文简洁、结构化回答用户问题。"
        user_content = question if not hint else f"{question}\n\n（提示：{hint}）"
        return await self._llm_call(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}],
            ctx,
        )

    async def _llm_call(self, messages: list[dict[str, str]], ctx: AgentRunContext) -> str:
        try:
            await _emit_progress(ctx, "llm_generating")
            return await _llm_call_maybe_stream(ctx=ctx, messages=messages)
        except Exception as e:
            logger.warning("OtherAgent LLM 调用失败: %s", e)
            return ""


class FiveAgentRouter:
    """五 Agent 路由器：先分类，再路由到四个业务 Agent。"""

    def __init__(self) -> None:
        self.classifier = IntentClassifierAgent()
        self.product_query = ProductQueryAgent()
        self.product_interpret = ProductInterpretAgent()
        self.product_compare = ProductCompareAgent()
        self.other = OtherAgent()

    def route(self, category: IntentCategory) -> BaseBusinessAgent:
        if category == "product_query":
            return self.product_query
        if category == "product_interpret":
            return self.product_interpret
        if category == "product_compare":
            return self.product_compare
        return self.other

