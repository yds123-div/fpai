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
import os
from typing import Any, Literal

from pkg.logger import get_logger

logger = get_logger(__name__)

IntentCategory = Literal["product_query", "product_interpret", "product_compare", "other"]

# 业务 Agent 拆分到独立模块，避免本文件过长
from agents.fund_agent.product_query.agent import ProductQueryAgent
from agents.fund_agent.product_interpret.agent import ProductInterpretAgent
from agents.fund_agent.product_compare.agent import ProductCompareAgent
from agents.fund_agent.other.agent import OtherAgent

# 公共运行时：上下文/LLM调用/进度回调等（避免循环导入）
from agents.fund_agent.runtime import AgentRunContext, BaseBusinessAgent, _emit_progress, _llm_call_maybe_stream


def _safe_first_str(x: Any) -> str:
    try:
        if x is None:
            return ""
        if isinstance(x, str):
            return x.strip()
        return str(x).strip()
    except Exception:
        return ""


def _parse_plan_output(s: str) -> dict[str, Any] | None:
    """
    解析 Coordinator 输出（预期 JSON）。
    期望：
    {
      "multi": true/false,
      "tasks": [{"type": "...", "question": "..."}],
      "final_instruction": "..."
    }
    """
    if not s:
        return None
    s = s.strip()
    try:
        obj = json.loads(s)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    tasks = obj.get("tasks")
    if tasks is not None and not isinstance(tasks, list):
        return None
    return obj


def _extract_json_object(text: str) -> str | None:
    """
    从模型输出中尽量提取 JSON object 字符串：
    - 先去掉 <think>...</think>
    - 支持 ```json ... ``` 代码块
    - 否则提取第一个顶层 {...}（按括号计数）
    """
    if not text:
        return None
    s = (text or "").strip()
    # 1) 去掉 think
    try:
        import re

        s = re.sub(r"<think>[\s\S]*?</think>", "", s, flags=re.IGNORECASE).strip()
    except Exception:
        s = s.strip()

    # 2) fenced code block
    if "```" in s:
        try:
            import re

            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, flags=re.IGNORECASE)
            if m:
                cand = (m.group(1) or "").strip()
                if cand.startswith("{") and cand.endswith("}"):
                    return cand
        except Exception:
            pass

    # 3) first top-level {...}
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None

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
    return "other"


class IntentClassifierAgent:
    """
    意图识别 Agent（框架版）。

    当前策略：
    - 先启发式分类（确保稳定）
    - 若后续你提供提示词/工具调用，可改为强制走 LLM 分类并输出 JSON
    """

    def classify(self, question: str) -> IntentCategory:
        return _heuristic_classify(question)


class CoordinatorAgent:
    """
    总控/规划 Agent（方式1）：负责识别多子任务并输出结构化 plan。
    - 使用 llm_chat（优先走 AgentScope ChatModel）生成 JSON plan
    - 失败则回退：单任务，按启发式分类
    """

    async def plan(self, question: str, ctx: "AgentRunContext") -> dict[str, Any]:
        q = (question or "").strip()
        if not q:
            return {"multi": False, "tasks": [], "final_instruction": ""}

        # 没有知识库可用时，没必要拆 kb_search
        kb_id = (ctx.knowledge_base_id or "").strip()

        system = """
你是一个“任务规划助手”，负责把用户输入拆分成可执行的子任务，并输出严格 JSON。

可用任务类型 type（只能从下面选）：
- product_compare：基金对比（通常包含“对比/比较/哪个好/差异”或出现两只及以上 6 位基金代码）
- product_interpret：单只基金解读/解析（通常只出现一只基金代码，并要求分析、风险、适合人群等）
- product_query：基金榜单/筛选/推荐（如“近期收益高、风险低、Top5、有哪些”）
- kb_search：知识库检索并返回依据（仅当用户明确提到“根据知识库/制度/文档/流程/条款/依据”等，且系统存在 knowledge_base_id 时才使用）
- free_answer：无需工具的通用回答

输出 JSON 结构如下（不得输出除 JSON 外的任何文字）：
{
  "multi": true|false,
  "tasks": [
    {"type": "product_compare|product_interpret|product_query|kb_search|free_answer", "question": "子问题（尽量短）"}
  ],
  "final_instruction": "如何融合 tasks 的结果形成最终答复（1-2 句）"
}

规则：
- 如果用户输入明显包含两个及以上不同子任务（例如“对比基金 + 同时问知识库流程/条款/依据”），multi=true，tasks 至少 2 个。
- 若用户没有选择知识库（knowledge_base_id 为空），禁止输出 kb_search。
- 子任务 question 必须是中文自然句，且能直接交给对应智能体执行。
""".strip()

        user = f"knowledge_base_id={(kb_id or '（空）')}\n用户输入：{q}"
        try:
            await _emit_progress(ctx, "coordinator_planning")
            from model_gateway.llm import llm_chat

            raw = await asyncio.to_thread(
                llm_chat,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                model=ctx.model_name,
                base_url=ctx.base_url,
                api_key=ctx.api_key,
            )
            raw_text = _safe_first_str(raw)
            json_text = _extract_json_object(raw_text) or raw_text
            plan = _parse_plan_output(json_text) or None
            if not plan:
                raise ValueError("plan json parse failed")
            # 归一化 tasks
            tasks = plan.get("tasks") or []
            norm: list[dict[str, Any]] = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tp = _safe_first_str(t.get("type"))
                qq = _safe_first_str(t.get("question"))
                if not tp or not qq:
                    continue
                if tp == "kb_search" and not kb_id:
                    continue
                if tp not in ("product_query", "product_interpret", "product_compare", "kb_search", "free_answer"):
                    continue
                norm.append({"type": tp, "question": qq})
            multi = bool(plan.get("multi")) and len(norm) >= 2
            if not norm:
                # 回退单任务
                cat = _heuristic_classify(q)
                return {"multi": False, "tasks": [{"type": cat, "question": q}], "final_instruction": ""}
            return {
                "multi": multi,
                "tasks": norm,
                "final_instruction": _safe_first_str(plan.get("final_instruction")),
            }
        except Exception as e:
            logger.warning("Coordinator plan failed, fallback to heuristic: %s", e)
            cat = _heuristic_classify(q)
            return {"multi": False, "tasks": [{"type": cat, "question": q}], "final_instruction": ""}
class FiveAgentRouter:
    """五 Agent 路由器：先分类，再路由到四个业务 Agent。"""

    def __init__(self) -> None:
        self.coordinator = CoordinatorAgent()
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

