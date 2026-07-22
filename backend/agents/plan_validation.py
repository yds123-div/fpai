# -*- coding: utf-8 -*-
"""
Coordinator plan 输出的三层校验与重试闭环（ADR-0001 生产实现）。

权威设计来源：docs/adr/0001-plan-output-validation-retry-loop.md

本模块是 plan 校验逻辑的**唯一归属**：
- 白名单 `VALID_TASK_TYPES`（决策 6，prompt 与校验器共同引用，消灭两处漂移）；
- JSON “救活”逻辑（`extract_json_object`/`try_fix_json`，决策 2：代码能救活的格式伤算通过，
  不消耗重试预算）-- 此前散落在 fund_agent_framework.py，现统一收编于此；
- `validate_plan`（L1 结构 + L2 白名单，纯函数，一次收集全部错误）；
- `build_retry_feedback`（续轮错误反馈：错误原因 + 白名单回灌）；
- `run_plan_with_retry`（重试闭环 -> 兜底 / 部分放行）。

L3 基金代码可信集合校验按 ADR 决策 4 不进重试环，本模块不含（生产维持现有确定性处理：
skill 查证 -> 可信集合 -> 清洗 / fund_code_not_found 中断）。

注：本模块由原型 backend/agents/proto_plan_validation.py 提升，去除腐蚀注入（腐蚀仅为
原型补分支覆盖的手段，生产不进）。`run_plan_with_retry` 在原型基础上改为 async +
async `llm_call` 回调，以便调用方在回调内保留“每次 30s 超时”语义（ADR 负面代价条款）。
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

# ---------------------------------------------------------------------------
# ADR-0001 决策 6：白名单唯一权威（prompt 与校验器共同引用，消灭两处漂移）
# 与 fund_agent_framework.COORDINATOR_DEFAULT_SYSTEM_PROMPT 中的 type 说明保持一致。
# ---------------------------------------------------------------------------
VALID_TASK_TYPES: tuple[str, ...] = (
    "product_query",
    "product_interpret",
    "product_compare",
    "other",
)

# 用于反馈消息回灌的 type 说明（与 system prompt 散文保持一致）
_TASK_TYPE_DESCRIPTIONS: dict[str, str] = {
    "product_compare": "基金对比（通常包含“对比/比较/哪个好/差异”或出现两只及以上 6 位基金代码/基金名称）",
    "product_interpret": "单只基金解读/解析（通常只出现一只基金代码/基金名称，并要求分析、风险、适合人群等）",
    "product_query": "基金榜单/筛选/推荐（如“近期收益高、风险低、Top5、有哪些”）",
    "other": "其它问答（统一交由 OtherAgent 处理：优先查询知识库，未命中再用大模型回答）",
}

MAX_PLAN_RETRIES = 2  # ADR-0001 决策 2：最多重试 2 次（即最多 1+2 次 LLM 调用）


# ---------------------------------------------------------------------------
# JSON “救活”逻辑（决策 2：代码能救活的格式伤算通过，不消耗重试预算）
# 唯一归属：fund_agent_framework.py 原有的同名函数已删除，统一引用此处。
# ---------------------------------------------------------------------------
def extract_json_object(text: str) -> str | None:
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
        s = re.sub(r"<think>[\s\S]*?</think>", "", s, flags=re.IGNORECASE).strip()
    except Exception:
        s = s.strip()

    # 2) fenced code block
    if "```" in s:
        try:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, flags=re.IGNORECASE)
            if m:
                cand = (m.group(1) or "").strip()
                if cand.startswith("{"):
                    fixed = try_fix_json(cand)
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
                fixed = try_fix_json(candidate)
                if fixed:
                    return fixed
                return candidate
    return None


def try_fix_json(json_str: str) -> str | None:
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
        open_count = json_str.count("{")
        close_count = json_str.count("}")
        if close_count > open_count:
            excess = close_count - open_count
            temp = json_str
            for _ in range(excess):
                last_brace = temp.rfind("}")
                if last_brace != -1:
                    temp = temp[:last_brace] + temp[last_brace + 1:]
            json.loads(temp)
            return temp
    except Exception:
        pass

    # 尝试修复：截取第一个完整 JSON 对象
    try:
        depth = 0
        for i, ch in enumerate(json_str):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = json_str[: i + 1]
                    json.loads(candidate)
                    return candidate
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# 解析（救活 + json.loads）：救得活 -> plan dict；救不活 -> None
# ---------------------------------------------------------------------------
def parse_plan(raw: str) -> dict[str, Any] | None:
    if not raw or not raw.strip():
        return None
    json_text = extract_json_object(raw)
    if not json_text:
        return None
    try:
        obj = json.loads(json_text)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


# ---------------------------------------------------------------------------
# 校验：L1 结构 + L2 白名单（ADR-0001 决策 2/6，纯函数，一次收集全部错误）
# ---------------------------------------------------------------------------
def _validate_plan_structured(raw: str) -> list[dict[str, Any]]:
    """返回结构化错误：{"layer": "L1"|"L2", "task_index": int|None, "message": str}
    task_index 为 None 表示全局错误（整个 plan 不可用），否则定位到 tasks[i]。"""
    errors: list[dict[str, Any]] = []

    def _err(layer: str, task_index: int | None, message: str) -> None:
        errors.append({"layer": layer, "task_index": task_index, "message": message})

    if not raw or not raw.strip():
        _err("L1", None, "输出为空")
        return errors

    plan = parse_plan(raw)
    if plan is None:
        _err("L1", None, "无法从输出中解析出合法 JSON 对象（已尝试剥除 think/代码块、修复多余 } 后仍失败）")
        return errors

    tasks = plan.get("tasks")
    if tasks is None:
        _err("L1", None, "缺少 tasks 字段")
        return errors
    if not isinstance(tasks, list):
        _err("L1", None, "tasks 必须是数组")
        return errors
    if not tasks:
        _err("L1", None, "tasks 为空数组：至少输出 1 个子任务")
        return errors

    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            _err("L1", i, "不是合法的子任务对象")
            continue
        tp = t.get("type")
        tp_s = tp.strip() if isinstance(tp, str) else ""
        if not tp_s:
            _err("L1", i, "缺少 type 字段（或为空）")
        elif tp_s not in VALID_TASK_TYPES:
            _err("L2", i, f'type="{tp_s}" 不是合法任务类型')
        qq = t.get("question")
        if not (isinstance(qq, str) and qq.strip()):
            _err("L1", i, "缺少 question 字段（或为空）")

    return errors


def validate_plan(raw: str) -> list[str]:
    """ADR-0001 决策 6 签名：validate_plan(raw) -> 错误清单（空列表 = 通过）。"""
    out: list[str] = []
    for e in _validate_plan_structured(raw):
        if e["task_index"] is None:
            out.append(f'[{e["layer"]}] {e["message"]}')
        else:
            out.append(f'[{e["layer"]}] tasks[{e["task_index"]}]：{e["message"]}')
    return out


# ---------------------------------------------------------------------------
# 续轮错误反馈（ADR-0001 决策 2）：
# ① 具体错误原因（精确到 tasks[i].type）；② 错误原文已在 assistant 消息中；
# ③ 可用 type 白名单回灌
# ---------------------------------------------------------------------------
def build_retry_feedback(errors: list[str]) -> str:
    lines = [
        "你上一次输出的 plan JSON 未通过校验（错误原文见上一条你的回复）。",
        "请修正后重新输出完整 plan JSON，且不要输出 JSON 以外的任何文字。",
        "",
        f"发现的问题（共 {len(errors)} 条）：",
    ]
    for i, e in enumerate(errors, 1):
        lines.append(f"{i}. {e}")
    lines.append("")
    lines.append("合法 type 白名单（tasks[i].type 只能从下面选）：")
    for tp in VALID_TASK_TYPES:
        lines.append(f"- {tp}：{_TASK_TYPE_DESCRIPTIONS[tp]}")
    lines.append("")
    lines.append("请直接输出修正后的完整 plan JSON。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 重试闭环（ADR-0001 决策 2/3）：校验 -> 反馈 -> 重试 -> 兜底 / 部分放行
# ---------------------------------------------------------------------------
async def run_plan_with_retry(
    messages: list[dict[str, str]],
    llm_call: Callable[[list[dict[str, str]]], Awaitable[str]],
) -> dict[str, Any]:
    """
    最多 1 + MAX_PLAN_RETRIES 次 LLM 调用。续轮 = 追加 assistant（错误输出原文）
    + user（build_retry_feedback 错误反馈）。

    llm_call 为 async 回调，由调用方负责“每次 30s 超时”等调用语义（ADR 负面代价条款：
    每次 30s 超时上限不变）。llm_call 抛出的异常（超时/网络）不在此处捕获--上抛给
    调用方走启发式兜底（与改造前“超时即启发式”行为一致）；本闭环只处理“模型输出可解析
    但校验不通过”的自愈型错误。

    返回：
      status      first_pass | retry_success | fallback_heuristic | partial_pass
      attempts    [{n, raw, errors}]（每次调用的原始输出与校验结果）
      events      审计事件序列（plan_validation_error / plan_retry_success /
                  plan_fallback_heuristic / plan_partial_drop），由调用方落 audit
      plan        最终可用 plan（fallback 时为 None；partial_pass 时仅含保留任务）
      dropped     部分放行时被丢弃的非法任务 [{index, task, reasons}]
      llm_calls   LLM 调用次数
    """
    history = list(messages)  # 不改调用方列表
    attempts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for n in range(1, MAX_PLAN_RETRIES + 2):  # 第 1..3 次调用
        raw = await llm_call(history)
        raw = raw if isinstance(raw, str) else str(raw or "")

        errors = validate_plan(raw)
        attempts.append({"n": n, "raw": raw, "errors": errors})

        if not errors:
            if n > 1:
                events.append({"event": "plan_retry_success", "attempt": n})
            return {
                "status": "first_pass" if n == 1 else "retry_success",
                "attempts": attempts,
                "events": events,
                "plan": parse_plan(raw),
                "dropped": [],
                "llm_calls": n,
            }

        structured = _validate_plan_structured(raw)
        events.append(
            {
                "event": "plan_validation_error",
                "attempt": n,
                "layers": sorted({e["layer"] for e in structured}),
                "errors": errors,
            }
        )
        if n <= MAX_PLAN_RETRIES:
            history = history + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": build_retry_feedback(errors)},
            ]

    # ---- 重试耗尽（ADR 决策 2/3）：能部分放行则部分放行，否则启发式兜底 ----
    final_raw = attempts[-1]["raw"]
    structured = _validate_plan_structured(final_raw)
    global_errors = [e for e in structured if e["task_index"] is None]
    plan = parse_plan(final_raw)
    if plan is not None and not global_errors:
        tasks = plan.get("tasks") or []
        bad_idx = sorted({e["task_index"] for e in structured if e["task_index"] is not None})
        kept = [t for i, t in enumerate(tasks) if i not in bad_idx]
        dropped = [
            {
                "index": i,
                "task": t,
                "reasons": [e["message"] for e in structured if e["task_index"] == i],
            }
            for i, t in enumerate(tasks)
            if i in bad_idx
        ]
        if kept:
            events.append(
                {
                    "event": "plan_partial_drop",
                    "attempt": len(attempts),
                    "dropped_count": len(dropped),
                    "kept_count": len(kept),
                }
            )
            return {
                "status": "partial_pass",
                "attempts": attempts,
                "events": events,
                "plan": {
                    "multi": bool(plan.get("multi")) and len(kept) >= 2,
                    "tasks": kept,
                    "final_instruction": plan.get("final_instruction") or "",
                },
                "dropped": dropped,
                "llm_calls": len(attempts),
            }

    events.append(
        {
            "event": "plan_fallback_heuristic",
            "attempt": len(attempts),
        }
    )
    return {
        "status": "fallback_heuristic",
        "attempts": attempts,
        "events": events,
        "plan": None,
        "dropped": [],
        "llm_calls": len(attempts),
    }
