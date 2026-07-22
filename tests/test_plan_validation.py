# -*- coding: utf-8 -*-
"""
ADR-0001 决策 7：plan 校验+重试闭环的测试（项目首个测试文件）。

测试路径说明：backend/pyproject.toml 配置 testpaths=["../tests"]、pythonpath=["."]，
因此测试置于仓库根 tests/，import 路径以 backend/ 为根（from agents.plan_validation import ...）。
运行：cd backend && python -m pytest ../tests/test_plan_validation.py -v
"""
from __future__ import annotations

import json

import pytest

from agents.plan_validation import (
    MAX_PLAN_RETRIES,
    VALID_TASK_TYPES,
    build_retry_feedback,
    parse_plan,
    run_plan_with_retry,
    validate_plan,
)


# ---------------------------------------------------------------------------
# 白名单单一权威（决策 6）
# ---------------------------------------------------------------------------
def test_valid_task_types_is_the_four_authoritative_types() -> None:
    assert VALID_TASK_TYPES == (
        "product_query",
        "product_interpret",
        "product_compare",
        "other",
    )


def test_max_plan_retries_is_two() -> None:
    """决策 2：最多重试 2 次（即最多 1+2=3 次 LLM 调用）。"""
    assert MAX_PLAN_RETRIES == 2


# ---------------------------------------------------------------------------
# validate_plan：L1 结构 + L2 白名单（决策 2/6，纯函数一次收集全部错误）
# ---------------------------------------------------------------------------
def _valid_plan_text() -> str:
    return json.dumps(
        {
            "multi": True,
            "tasks": [
                {"type": "product_compare", "question": "对比 000001 和 000002"},
                {"type": "other", "question": "基金定投怎么开户"},
            ],
            "final_instruction": "先给对比再回答开户",
        },
        ensure_ascii=False,
    )


def test_validate_plan_legal() -> None:
    assert validate_plan(_valid_plan_text()) == []


def test_validate_plan_empty_input() -> None:
    assert validate_plan("") == ["[L1] 输出为空"]
    assert validate_plan("   \n  ") == ["[L1] 输出为空"]


def test_validate_plan_unparseable_json() -> None:
    # 截断到救活逻辑无法修复（括号永不闭合）
    bad = '{"multi": true, "tasks": [{"type": "product_'
    errs = validate_plan(bad)
    assert len(errs) == 1
    assert errs[0].startswith("[L1]")
    assert "解析" in errs[0]


def test_validate_plan_rescuable_format_passes() -> None:
    """决策 2：代码块包裹、多余 } 等代码能救活的格式伤算通过，不消耗重试预算。"""
    inner = json.dumps(
        {
            "multi": False,
            "tasks": [{"type": "product_query", "question": "近期收益高的基金"}],
            "final_instruction": "",
        },
        ensure_ascii=False,
    )
    # 用 ```json 代码块包裹 + 末尾多一个 }
    wrapped = f"```json\n{inner}}}\n```"
    assert validate_plan(wrapped) == []


def test_validate_plan_missing_tasks() -> None:
    errs = validate_plan(json.dumps({"multi": False, "final_instruction": ""}, ensure_ascii=False))
    assert len(errs) == 1
    assert errs[0].startswith("[L1]")
    assert "tasks" in errs[0]


def test_validate_plan_empty_tasks_array() -> None:
    errs = validate_plan(json.dumps({"multi": False, "tasks": []}, ensure_ascii=False))
    assert errs == ["[L1] tasks 为空数组：至少输出 1 个子任务"]


def test_validate_plan_hallucinated_type_all_bad() -> None:
    text = json.dumps(
        {
            "multi": False,
            "tasks": [{"type": "fund_analysis", "question": "分析 000001"}],
            "final_instruction": "",
        },
        ensure_ascii=False,
    )
    errs = validate_plan(text)
    assert len(errs) == 1
    assert errs[0].startswith("[L2]")
    assert "tasks[0]" in errs[0]
    assert "fund_analysis" in errs[0]


def test_validate_plan_partial_hallucination_locates_bad_index() -> None:
    text = json.dumps(
        {
            "multi": True,
            "tasks": [
                {"type": "product_compare", "question": "对比 000001 和 000002"},
                {"type": "kb_search", "question": "定投规则"},  # 旧/幻觉 type
            ],
            "final_instruction": "",
        },
        ensure_ascii=False,
    )
    errs = validate_plan(text)
    assert len(errs) == 1
    assert "tasks[1]" in errs[0]
    assert errs[0].startswith("[L2]")


def test_validate_plan_empty_question() -> None:
    text = json.dumps(
        {
            "multi": False,
            "tasks": [{"type": "product_query", "question": "   "}],
            "final_instruction": "",
        },
        ensure_ascii=False,
    )
    errs = validate_plan(text)
    assert len(errs) == 1
    assert errs[0].startswith("[L1]")
    assert "tasks[0]" in errs[0]
    assert "question" in errs[0]


def test_validate_plan_collects_multiple_errors_at_once() -> None:
    """决策 6：一次收集全部错误（而非短路返回第一个）。"""
    text = json.dumps(
        {
            "multi": True,
            "tasks": [
                {"type": "fund_analysis", "question": "   "},  # L2 幻觉 + L1 空 question
                {"type": "other", "question": "正常问题"},
            ],
            "final_instruction": "",
        },
        ensure_ascii=False,
    )
    errs = validate_plan(text)
    assert len(errs) == 2
    assert any("tasks[0]" in e and e.startswith("[L2]") for e in errs)
    assert any("tasks[0]" in e and e.startswith("[L1]") for e in errs)


# ---------------------------------------------------------------------------
# parse_plan：救活 + json.loads
# ---------------------------------------------------------------------------
def test_parse_plan_strips_think_block() -> None:
    inner = json.dumps({"multi": False, "tasks": [{"type": "other", "question": "你好"}]}, ensure_ascii=False)
    raw = f"<think>some reasoning</think>{inner}"
    assert parse_plan(raw) is not None
    assert parse_plan(raw)["tasks"][0]["type"] == "other"


def test_parse_plan_returns_none_for_garbage() -> None:
    assert parse_plan("完全没有 json 的纯文本") is None
    assert parse_plan("") is None


# ---------------------------------------------------------------------------
# build_retry_feedback：续轮错误反馈（决策 2）
# ---------------------------------------------------------------------------
def test_build_retry_feedback_contains_count_whitelist_and_instruction() -> None:
    errs = ["[L2] tasks[0]：type=\"fund_analysis\" 不是合法任务类型"]
    msg = build_retry_feedback(errs)
    assert "共 1 条" in msg
    # 白名单 4 类全部回灌
    for tp in VALID_TASK_TYPES:
        assert tp in msg
    assert "请直接输出修正后的完整 plan JSON" in msg
    # 错误原文精确到病灶
    assert "tasks[0]" in msg
    assert "fund_analysis" in msg


# ---------------------------------------------------------------------------
# run_plan_with_retry：重试环分支（决策 2/3），stub 异步 llm_call
# ---------------------------------------------------------------------------
def _stub(outputs: list[str]):
    """构造异步 llm_call stub：按序消费 outputs，越界则重复最后一个。"""
    state = {"i": 0}

    async def _call(messages):
        i = state["i"]
        state["i"] = min(i + 1, len(outputs) - 1)
        return outputs[i]

    return _call


@pytest.mark.asyncio
async def test_retry_first_pass() -> None:
    """首次即通过：1 次调用，无审计事件。"""
    result = await run_plan_with_retry(
        [{"role": "user", "content": "q"}],
        _stub([_valid_plan_text()]),
    )
    assert result["status"] == "first_pass"
    assert result["llm_calls"] == 1
    assert result["events"] == []
    assert result["dropped"] == []
    assert result["plan"] is not None
    assert len(result["plan"]["tasks"]) == 2


@pytest.mark.asyncio
async def test_retry_success_on_second_attempt() -> None:
    """首轮烂 JSON -> 反馈 -> 第 2 次自愈成功。"""
    result = await run_plan_with_retry(
        [{"role": "user", "content": "q"}],
        _stub(['{"multi": false, "tasks": [{"type": "product_', _valid_plan_text()]),
    )
    assert result["status"] == "retry_success"
    assert result["llm_calls"] == 2
    event_types = [e["event"] for e in result["events"]]
    assert event_types == ["plan_validation_error", "plan_retry_success"]
    assert result["plan"] is not None


@pytest.mark.asyncio
async def test_retry_exhausted_fallback_heuristic() -> None:
    """三次全败（不可解析）-> 启发式兜底，plan=None。"""
    result = await run_plan_with_retry(
        [{"role": "user", "content": "q"}],
        _stub(['{"multi": false, "tasks": [{"type": "product_']),
    )
    assert result["status"] == "fallback_heuristic"
    assert result["plan"] is None
    assert result["llm_calls"] == MAX_PLAN_RETRIES + 1  # 3
    event_types = [e["event"] for e in result["events"]]
    # 3 次校验失败事件 + 1 次兜底
    assert event_types.count("plan_validation_error") == MAX_PLAN_RETRIES + 1
    assert event_types[-1] == "plan_fallback_heuristic"


@pytest.mark.asyncio
async def test_retry_exhausted_partial_pass() -> None:
    """部分幻觉：重试耗尽后丢弃非法任务、保留合法任务继续执行（决策 3）。"""
    partial = json.dumps(
        {
            "multi": True,
            "tasks": [
                {"type": "product_compare", "question": "对比 000001 和 000002"},
                {"type": "fund_analysis", "question": "分析 000001"},  # 幻觉 type
            ],
            "final_instruction": "",
        },
        ensure_ascii=False,
    )
    result = await run_plan_with_retry(
        [{"role": "user", "content": "q"}],
        _stub([partial, partial, partial]),
    )
    assert result["status"] == "partial_pass"
    assert result["llm_calls"] == MAX_PLAN_RETRIES + 1
    # 保留合法任务
    assert result["plan"] is not None
    assert len(result["plan"]["tasks"]) == 1
    assert result["plan"]["tasks"][0]["type"] == "product_compare"
    # 丢弃非法任务有记录
    assert len(result["dropped"]) == 1
    assert result["dropped"][0]["index"] == 1
    assert result["dropped"][0]["task"]["type"] == "fund_analysis"
    event_types = [e["event"] for e in result["events"]]
    assert event_types[-1] == "plan_partial_drop"


@pytest.mark.asyncio
async def test_retry_does_not_mutate_input_messages() -> None:
    messages = [{"role": "user", "content": "q"}]
    snapshot = [dict(m) for m in messages]
    await run_plan_with_retry(
        messages,
        _stub(['{"multi": false, "tasks": [{"type": "product_', _valid_plan_text()]),
    )
    assert messages == snapshot


@pytest.mark.asyncio
async def test_retry_feedback_appended_to_history_for_next_call() -> None:
    """续轮 = 追加 assistant（错误原文）+ user（错误反馈），让模型自愈（决策 2）。"""
    seen: list[list[dict]] = []

    async def _call(messages):
        seen.append([dict(m) for m in messages])
        return _valid_plan_text()  # 首次就通过，触发不了续轮；改用下面 stub

    # 重新构造：首次失败、二次成功，检查第 2 次收到的历史含 assistant+user 反馈
    state = {"i": 0}

    async def _call2(messages):
        seen.append([dict(m) for m in messages])
        i = state["i"]
        state["i"] += 1
        return ['{"multi": false, "tasks": [{"type": "bad_', _valid_plan_text()][i]

    await run_plan_with_retry([{"role": "user", "content": "q"}], _call2)
    assert len(seen) == 2
    second = seen[1]
    # 第 2 次历史 = 原始 user + assistant(错误原文) + user(反馈)
    assert len(second) == 3
    assert second[1]["role"] == "assistant"
    assert second[2]["role"] == "user"
    assert "合法 type 白名单" in second[2]["content"]


# ---------------------------------------------------------------------------
# 集成接线：CoordinatorAgent.plan() 实际使用 run_plan_with_retry（决策 7 动机：
# 机制坏了会静默退化为旧行为，需测试守住接线，防有人改回单次调用）
# ---------------------------------------------------------------------------
async def test_coordinator_plan_wires_retry_and_propagates_dropped(monkeypatch) -> None:
    import agents.fund_agent_framework as faf
    from agents.fund_agent.runtime import AgentRunContext

    canned_plan = {
        "multi": True,
        "tasks": [{"type": "product_compare", "question": "对比 000001 和 000002"}],
        "final_instruction": "",
    }
    canned_dropped = [
        {
            "index": 1,
            "task": {"type": "fund_analysis", "question": "分析"},
            "reasons": ['type="fund_analysis" 不是合法任务类型'],
        }
    ]
    called: list[tuple] = []

    async def _fake_retry(messages, llm_call):
        called.append((messages, llm_call))
        return {
            "status": "partial_pass",
            "attempts": [{"n": 3, "raw": "...", "errors": ["..."]}],
            "events": [{"event": "plan_partial_drop", "attempt": 3, "dropped_count": 1, "kept_count": 1}],
            "plan": canned_plan,
            "dropped": canned_dropped,
            "llm_calls": 3,
        }

    monkeypatch.setattr(faf, "run_plan_with_retry", _fake_retry)

    ctx = AgentRunContext(model_name="x", base_url="http://x", api_key="k")  # answer_id 留空
    router = faf.CoordinatorAgent()
    # “另外”复合标记绕过 fast-path，使其走到 run_plan_with_retry
    plan = await router.plan("对比000001和000002，另外基金定投怎么开户", ctx)

    # 接线确认：plan() 确实调用了 run_plan_with_retry
    assert len(called) == 1
    messages, _ = called[0]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    # 部分放行：合法任务保留、dropped 透传
    assert plan["tasks"][0]["type"] == "product_compare"
    assert plan["dropped"] == canned_dropped


def test_emit_plan_audit_events_writes_when_answer_id_present(monkeypatch) -> None:
    import audit
    from agents.fund_agent.runtime import AgentRunContext
    import agents.fund_agent_framework as faf

    recorded: list[dict] = []

    def _fake_append(answer_id, event_type, payload, *, session_id=None, user_id=None, **kw):
        recorded.append({"answer_id": answer_id, "event_type": event_type, "payload": payload, "session_id": session_id, "user_id": user_id})

    monkeypatch.setattr(audit, "append_event", _fake_append)

    ctx = AgentRunContext(session_id="s1", user_id="u1", answer_id="aid-1")
    events = [
        {"event": "plan_validation_error", "attempt": 1, "layers": ["L2"], "errors": ["[L2] tasks[0]：bad"]},
        {"event": "plan_retry_success", "attempt": 2},
    ]
    faf._emit_plan_audit_events(ctx, events)

    assert len(recorded) == 2
    assert recorded[0]["event_type"] == "plan_validation_error"
    assert recorded[0]["answer_id"] == "aid-1"
    assert recorded[0]["session_id"] == "s1"
    assert recorded[0]["user_id"] == "u1"
    # payload 去掉 event 键
    assert "event" not in recorded[0]["payload"]
    assert recorded[0]["payload"]["attempt"] == 1
    assert recorded[1]["event_type"] == "plan_retry_success"


def test_emit_plan_audit_events_skips_when_no_answer_id(monkeypatch) -> None:
    import audit
    from agents.fund_agent.runtime import AgentRunContext
    import agents.fund_agent_framework as faf

    called: list = []

    def _fake_append(*a, **k):
        called.append(a)

    monkeypatch.setattr(audit, "append_event", _fake_append)

    ctx = AgentRunContext()  # answer_id 默认 None
    faf._emit_plan_audit_events(ctx, [{"event": "plan_validation_error", "attempt": 1}])
    assert called == []  # 无 answer_id 不落审计

