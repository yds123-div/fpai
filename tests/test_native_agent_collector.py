# -*- coding: utf-8 -*-
"""T6 (#24)：structured_outputs collector 纯函数单测。

覆盖验收：
- ``select_output_mode``：单只/榜单 -> ``single``、多只对比 -> ``compare``
- ``build_structured_output``：按模式跑 ``build_single_output`` / ``build_compare_output``，
  形状正确（type/mode/sections/charts/text）；无基金 payload 时返回 None。

纯函数不依赖 AgentScope；``StructuredOutputsCollector`` 中间件壳的端到端验证在
``test_native_agent.py``（脚本化假 ``ChatModelBase`` + 桩工具 seam）。

运行：cd backend && python -m pytest ../tests/test_native_agent_collector.py -c pyproject.toml -v
"""
from __future__ import annotations

from typing import Any

from agents.native_agent.structured_collector import (
    CapturedToolResult,
    build_structured_output,
    pick_primary_payload,
    select_output_mode,
)
from pkg.fund_types import FUND_ANALYSIS_TYPE


def _fund(sym: str) -> dict[str, Any]:
    """最小基金 dict（builder 各 format_* 对缺字段 graceful 返回 None）。"""
    return {"symbol": sym, "basic_info": {"ok": True, "data": []}}


def _detail(funds: list[dict[str, Any]]) -> dict[str, Any]:
    """query_fund_detail 结果（payload 包装）。"""
    return {"payload": {"ok": True, "funds": funds}}


def _rank(funds: list[dict[str, Any]]) -> dict[str, Any]:
    """query_fund_rank 结果（无 payload 包装，自身带 ok）。"""
    return {"ok": True, "funds": funds}


# ---------------------------------------------------------------------------
# select_output_mode
# ---------------------------------------------------------------------------
def test_mode_single_for_single_fund_detail() -> None:
    cap = [CapturedToolResult("query_fund_detail", _detail([_fund("005827")]))]
    assert select_output_mode(cap) == "single"


def test_mode_compare_for_two_funds_detail() -> None:
    cap = [CapturedToolResult("query_fund_detail", _detail([_fund("005827"), _fund("161725")]))]
    assert select_output_mode(cap) == "compare"


def test_mode_single_for_rank_list_even_if_many_funds() -> None:
    # 榜单返回多只基金，但属「榜单短版」而非「对比」 -> single
    cap = [
        CapturedToolResult(
            "query_fund_rank",
            _rank([_fund("005827"), _fund("161725"), _fund("110011")]),
        )
    ]
    assert select_output_mode(cap) == "single"


def test_mode_single_when_only_resolve_or_kb() -> None:
    cap = [
        CapturedToolResult(
            "resolve_fund_code",
            {"ok": True, "mode": "name_to_code", "matches": []},
        )
    ]
    assert select_output_mode(cap) == "single"


def test_mode_single_when_empty() -> None:
    assert select_output_mode([]) == "single"


def test_mode_compare_wins_when_any_detail_has_multi_funds() -> None:
    # 模型先查单只、再扩到对比 -> 取最宽者（compare）
    cap = [
        CapturedToolResult("query_fund_detail", _detail([_fund("005827")])),
        CapturedToolResult(
            "query_fund_detail",
            _detail([_fund("005827"), _fund("161725")]),
        ),
    ]
    assert select_output_mode(cap) == "compare"


# ---------------------------------------------------------------------------
# pick_primary_payload
# ---------------------------------------------------------------------------
def test_pick_prefers_detail_over_rank() -> None:
    cap = [
        CapturedToolResult("query_fund_rank", _rank([_fund("005827")])),
        CapturedToolResult("query_fund_detail", _detail([_fund("161725")])),
    ]
    assert pick_primary_payload(cap) == cap[1].payload


def test_pick_falls_back_to_rank_when_no_detail() -> None:
    cap = [CapturedToolResult("query_fund_rank", _rank([_fund("005827")]))]
    assert pick_primary_payload(cap) == cap[0].payload


def test_pick_returns_none_when_only_resolve_or_kb() -> None:
    cap = [CapturedToolResult("resolve_fund_code", {"ok": True, "matches": []})]
    assert pick_primary_payload(cap) is None


def test_pick_takes_last_detail_when_multiple() -> None:
    cap = [
        CapturedToolResult("query_fund_detail", _detail([_fund("005827")])),
        CapturedToolResult("query_fund_detail", _detail([_fund("161725")])),
    ]
    assert pick_primary_payload(cap) == cap[1].payload


# ---------------------------------------------------------------------------
# build_structured_output
# ---------------------------------------------------------------------------
def test_build_single_shape_for_one_fund() -> None:
    cap = [CapturedToolResult("query_fund_detail", _detail([_fund("005827")]))]
    out = build_structured_output(cap, "分析文本")
    assert out is not None
    assert out["type"] == FUND_ANALYSIS_TYPE
    assert out["mode"] == "single"
    assert out["text"] == "分析文本"
    assert isinstance(out["sections"], list)
    assert isinstance(out["charts"], list)


def test_build_compare_shape_for_two_funds() -> None:
    cap = [
        CapturedToolResult(
            "query_fund_detail",
            _detail([_fund("005827"), _fund("161725")]),
        )
    ]
    out = build_structured_output(cap, "对比文本")
    assert out is not None
    assert out["type"] == FUND_ANALYSIS_TYPE
    assert out["mode"] == "compare"
    assert out["text"] == "对比文本"


def test_build_single_for_rank_list() -> None:
    cap = [CapturedToolResult("query_fund_rank", _rank([_fund("005827"), _fund("161725")]))]
    out = build_structured_output(cap, "榜单文本")
    assert out is not None
    assert out["mode"] == "single"


def test_build_returns_none_when_no_fund_payload() -> None:
    cap = [CapturedToolResult("resolve_fund_code", {"ok": True, "matches": []})]
    assert build_structured_output(cap, "txt") is None
