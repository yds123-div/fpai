# -*- coding: utf-8 -*-
"""
理财 Agent 框架（先搭骨架，后续再填提示词/工具调用）：

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
from dataclasses import replace
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
from agents.fund_agent.runtime import (
    AgentRunContext,
    BaseBusinessAgent,
    _emit_progress,
    _llm_call_maybe_stream,
    resolve_agent_skill_keys,
    resolve_agent_overrides,
    run_configured_skills,
)


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
    - 尝试修复常见的 JSON 语法错误
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
                if cand.startswith("{"):
                    # 尝试验证和修复 JSON
                    fixed = _try_fix_json(cand)
                    if fixed:
                        return fixed
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
                candidate = s[start : i + 1]
                # 尝试验证和修复 JSON
                fixed = _try_fix_json(candidate)
                if fixed:
                    return fixed
                return candidate
    return None


def _try_fix_json(json_str: str) -> str | None:
    """
    尝试修复常见的 JSON 语法错误：
    1. 验证 JSON 是否有效
    2. 如果无效，尝试修复常见问题（如多余的右花括号）
    """
    if not json_str:
        return None
    
    # 先尝试直接解析
    try:
        json.loads(json_str)
        return json_str
    except Exception:
        pass
    
    # 尝试修复：移除末尾多余的 }
    try:
        # 统计花括号数量
        open_count = json_str.count("{")
        close_count = json_str.count("}")
        
        if close_count > open_count:
            # 从末尾移除多余的 }
            excess = close_count - open_count
            temp = json_str
            for _ in range(excess):
                # 找到最后一个 }
                last_brace = temp.rfind("}")
                if last_brace != -1:
                    temp = temp[:last_brace] + temp[last_brace + 1:]
            
            # 验证修复后的 JSON
            json.loads(temp)
            return temp
    except Exception:
        pass
    
    # 尝试修复：移除末尾多余的 } 之前的内容
    try:
        import re
        # 查找最后一个完整的 JSON 对象
        # 从第一个 { 开始，找到匹配的 }
        depth = 0
        for i, ch in enumerate(json_str):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = json_str[:i + 1]
                    json.loads(candidate)
                    return candidate
    except Exception:
        pass
    
    return None

def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return s


def _extract_codes_from_text(text: str) -> list[str]:
    import re
    s = _safe_first_str(text)
    if not s:
        return []
    return re.findall(r"(?<!\d)\d{6}(?!\d)", s)


def _remove_untrusted_codes_from_question(question: str) -> str:
    """
    清理 question 中可能由 LLM 臆测的基金代码，避免错误代码下钻到业务 agent。
    """
    import re
    q = _safe_first_str(question)
    if not q:
        return q
    # 移除“（基金代码：xxxxxx）/基金代码：xxxxxx”这类附注
    q = re.sub(r"[（(]\s*基金代码\s*[：:]\s*(?:\d{6})(?:[、,，]\s*\d{6})*\s*[)）]", "", q)
    q = re.sub(r"基金代码\s*[：:]\s*(?:\d{6})(?:[、,，]\s*\d{6})*", "", q)
    # 移除孤立 6 位数字
    q = re.sub(r"(?<!\d)\d{6}(?!\d)", "", q)
    # 清理多余空白与标点边界
    q = re.sub(r"\s{2,}", " ", q).strip(" ，,;；。")
    return q.strip()


def _extract_codes_from_planner_skill_payload(payload: Any) -> list[str]:
    """
    从 task_planner skill 返回结果中提取 6 位基金代码。
    兼容结构：
    - {"skill":"fund_name_to_code","payload":{"ok":true,"codes":[...]}}
    - {"skill":"fund_name_to_code","payload":{"ok":true,"matches":[{"code":"..."}]}}
    """
    out: list[str] = []
    if not isinstance(payload, dict):
        return out
    p = payload.get("payload")
    if not isinstance(p, dict):
        return out
    if p.get("ok") is not True:
        return out

    # 1) 直接 codes
    raw_codes = p.get("codes")
    if isinstance(raw_codes, list):
        for c in raw_codes:
            s = _safe_first_str(c)
            if s.isdigit() and len(s) == 6:
                out.append(s)

    # 2) matches[].code
    raw_matches = p.get("matches")
    if isinstance(raw_matches, list):
        for m in raw_matches:
            if not isinstance(m, dict):
                continue
            s = _safe_first_str(m.get("code"))
            if s.isdigit() and len(s) == 6:
                out.append(s)

    # 去重保序
    uniq: list[str] = []
    seen: set[str] = set()
    for c in out:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return uniq


def _extract_name_code_pairs_from_planner_skill_payload(payload: Any) -> list[tuple[str, str]]:
    """
    从 task_planner skill 返回结果提取 (基金名称, 基金代码) 对。
    仅使用 payload.matches 里的 name/code 字段。
    """
    out: list[tuple[str, str]] = []
    if not isinstance(payload, dict):
        return out
    p = payload.get("payload")
    if not isinstance(p, dict):
        return out
    if p.get("ok") is not True:
        return out
    raw_matches = p.get("matches")
    if not isinstance(raw_matches, list):
        return out
    for m in raw_matches:
        if not isinstance(m, dict):
            continue
        name = _safe_first_str(m.get("name"))
        code = _safe_first_str(m.get("code"))
        if not name or not code or (not code.isdigit()) or len(code) != 6:
            continue
        out.append((name, code))
    return out


def _planner_skill_indicates_no_code(payload: Any) -> bool:
    """
    判断 task_planner 的基金名称转代码结果是否明确表示“未查到代码”。
    """
    if not isinstance(payload, dict):
        return False
    p = payload.get("payload")
    if not isinstance(p, dict):
        return False
    if p.get("ok") is True:
        return False
    mode = _safe_first_str(p.get("mode"))
    return mode in ("no_match", "no_keyword", "no_data", "fetch_error")


def _pick_codes_for_question(question: str, name_code_pairs: list[tuple[str, str]], fallback_codes: list[str]) -> list[str]:
    """
    基于子任务 question 匹配更精准的基金代码：
    - 优先用名称命中 question 的 code（按名称长度降序，避免短词误命中）
    - 未命中时回退到全局代码列表
    """
    q = _safe_first_str(question)
    if not q:
        return list(fallback_codes)

    picked: list[str] = []
    for name, code in sorted(name_code_pairs, key=lambda x: len(x[0]), reverse=True):
        if name in q and code not in picked:
            picked.append(code)
    if picked:
        return picked
    return list(fallback_codes)


def _rewrite_task_question_with_codes(question: str, codes: list[str], task_type: str) -> str:
    """
    将规划阶段得到的基金代码注入到子任务 question，确保下游 agent 可直接消费。
    """
    q = _safe_first_str(question)
    if not q or not codes:
        return q
    # question 中已含代码则不重复注入
    import re
    if re.search(r"(?<!\d)\d{6}(?!\d)", q):
        return q
    if task_type == "product_compare" and len(codes) >= 2:
        return f"{q}（基金代码：{'、'.join(codes[:5])}）"
    return f"{q}（基金代码：{codes[0]}）"


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


COORDINATOR_DEFAULT_SYSTEM_PROMPT = """
你是一个“任务规划助手”，负责把用户输入拆分成可执行的子任务，并输出严格 JSON。

可用任务类型 type（只能从下面选）：
- product_compare：基金对比（通常包含“对比/比较/哪个好/差异”或出现两只及以上 6 位基金代码/基金名称）
- product_interpret：单只基金解读/解析（通常只出现一只基金代码/基金名称，并要求分析、风险、适合人群等）
- product_query：基金榜单/筛选/推荐（如“近期收益高、风险低、Top5、有哪些”）
- other：其它问答（统一交由 OtherAgent 处理：优先查询知识库，未命中再用大模型回答）

输出 JSON 结构如下（不得输出除 JSON 外的任何文字）：
{
  "multi": true|false,
  "tasks": [
    {"type": "product_compare|product_interpret|product_query|other", "question": "子问题（尽量短）"}
  ],
  "final_instruction": "如何融合 tasks 的结果形成最终答复（1-2 句）"
}

规则：
- 如果用户输入明显包含两个及以上不同子任务（例如“对比基金 + 同时问制度流程”），multi=true，tasks 至少 2 个。
- 子任务 question 必须是中文自然句，且能直接交给对应智能体执行。
""".strip()


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
        user_input_codes = _extract_codes_from_text(q)

        # 对“你好/闲聊”等纯客套输入走启发式短路：
        # - 避免先调用一次 LLM 做 plan（你日志里会看到 tasks=[] 的那次）
        # - 直接把任务分给 other，后续由 OtherAgent 自行生成回答
        try:
            import re as _re

            def _is_chitchat(text: str) -> bool:
                # 若出现基金代码，优先当作产品问题处理
                if _re.search(r"(?<!\d)\d{6}(?!\d)", text or ""):
                    return False
                t = (text or "").strip()
                triggers = (
                    "你好",
                    "您好",
                    "在吗",
                    "哈喽",
                    "你好呀",
                    "早上好",
                    "晚上好",
                    "谢谢",
                    "感谢",
                    "怎么称呼",
                    "你是谁",
                    "你叫什么",
                    "再见",
                    "拜拜",
                    "闲聊",
                    "聊天",
                    "打个招呼",
                    "打招呼",
                )
                return any(x in t for x in triggers)

            cat_for_short_circuit = _heuristic_classify(q)
            if cat_for_short_circuit == "other" and _is_chitchat(q):
                return {"multi": False, "tasks": [{"type": "other", "question": q}], "final_instruction": ""}
        except Exception:
            # 短路失败不影响主流程
            pass

        # 没有知识库可用时，没必要拆 kb_search
        kb_id = (ctx.knowledge_base_id or "").strip()

        planner_ctx = replace(ctx)
        system_prompt, planner_ctx = resolve_agent_overrides(
            agent_key="task_planner",
            ctx=planner_ctx,
            default_system_prompt=COORDINATOR_DEFAULT_SYSTEM_PROMPT,
        )

        # 任务规划器也支持配置 skill_keys（例如 fund_name_to_code）：
        # 将 skill 结果注入规划提示，帮助 Planner 更准确拆解/改写子问题。
        planner_skill_payload: Any = None
        try:
            planner_skill_keys = resolve_agent_skill_keys(agent_key="task_planner") or []
            if planner_skill_keys:
                await _emit_progress(ctx, "coordinator_skill_fetching")
                try:
                    planner_skill_payload = await asyncio.wait_for(
                        run_configured_skills(
                            skill_keys=planner_skill_keys,
                            question=q,
                            ctx=planner_ctx,
                        ),
                        timeout=15,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Coordinator planner skills timeout (15s)")
                    planner_skill_payload = None
        except Exception as e:
            logger.warning("Coordinator planner skills failed: %s", e)
            planner_skill_payload = None

        user = (
            f"knowledge_base_id={(kb_id or '（空）')}\n"
            f"用户输入：{q}\n"
            f"任务规划辅助数据（来自 task_planner skills，可为空）："
            f"{json.dumps(planner_skill_payload, ensure_ascii=False)}"
        )
        try:
            await _emit_progress(ctx, "coordinator_planning")
            from model_gateway.llm import llm_chat

            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(
                        llm_chat,
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}],
                        model=planner_ctx.model_name,
                        base_url=planner_ctx.base_url,
                        api_key=planner_ctx.api_key,
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning("Coordinator plan llm_chat timeout (30s), fallback to heuristic")
                cat = _heuristic_classify(q)
                return {"multi": False, "tasks": [{"type": cat, "question": q}], "final_instruction": ""}
            raw_text = _safe_first_str(raw)
            json_text = _extract_json_object(raw_text) or raw_text
            plan = _parse_plan_output(json_text) or None
            if not plan:
                raise ValueError("plan json parse failed")
            # 归一化 tasks
            tasks = plan.get("tasks") or []
            planner_codes = _extract_codes_from_planner_skill_payload(planner_skill_payload)
            planner_name_code_pairs = _extract_name_code_pairs_from_planner_skill_payload(planner_skill_payload)
            norm: list[dict[str, Any]] = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tp = _safe_first_str(t.get("type"))
                qq = _safe_first_str(t.get("question"))
                if not tp or not qq:
                    continue
                # 兼容旧提示词输出：kb_search/free_answer 统一映射到 other
                if tp in ("kb_search", "free_answer"):
                    tp = "other"
                if tp not in ("product_query", "product_interpret", "product_compare", "other"):
                    continue
                if tp in ("product_query", "product_interpret", "product_compare"):
                    qq_before = qq
                    codes_for_task = _pick_codes_for_question(qq, planner_name_code_pairs, planner_codes)
                    if codes_for_task:
                        qq = _rewrite_task_question_with_codes(qq, codes_for_task, tp)
                        logger.debug(
                            "planner task code mapping: type=%s, question='%s' -> '%s', matched_codes=%s",
                            tp,
                            qq_before,
                            qq,
                            codes_for_task,
                        )
                    else:
                        # 未命中任何可信 code 时，清理规划器可能臆测出的代码
                        qq_codes = _extract_codes_from_text(qq)
                        trusted = set(user_input_codes + planner_codes)
                        if any(c not in trusted for c in qq_codes):
                            qq = _remove_untrusted_codes_from_question(qq)
                            logger.debug(
                                "planner task code sanitized: type=%s, question='%s' -> '%s', task_codes=%s, trusted_codes=%s",
                                tp,
                                qq_before,
                                qq,
                                qq_codes,
                                list(trusted),
                            )
                norm.append({"type": tp, "question": qq})

            # 强约束：若用户未提供代码，且名称转代码也未命中，则直接中断，避免错误下钻。
            requires_code = any(
                isinstance(x, dict) and _safe_first_str(x.get("type")) in ("product_query", "product_interpret", "product_compare")
                for x in norm
            )
            if requires_code and (not user_input_codes) and (not planner_codes) and _planner_skill_indicates_no_code(planner_skill_payload):
                return {
                    "multi": False,
                    "tasks": [],
                    "final_instruction": "",
                    "abort": {
                        "reason": "fund_code_not_found",
                        "message": "未查询到基金代码，请补充准确的基金名称或直接提供6位基金代码。",
                    },
                }
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
class FundAgentRouter:
    """基金业务 Agent 路由器：先分类，再路由到四个业务 Agent。"""

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

