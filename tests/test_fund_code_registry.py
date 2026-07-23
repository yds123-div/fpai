# -*- coding: utf-8 -*-
"""
T3（#21）：fund_code_registry 单测。

测试路径说明：backend/pyproject.toml 配置 testpaths=["../tests"]、pythonpath=["."]，
运行：cd backend && python -m pytest ../tests/test_fund_code_registry.py -v

栅栏 #1 基座：fund_code_registry 持有 akshare 基金列表 + 缓存，暴露
is_trusted / resolve。本文件用 monkeypatch 替换 _load_fund_list 注入确定性数据，
不触网。
"""
from __future__ import annotations

import json

import pytest

from agents.skills import fund_code_registry as registry
from agents.skills.fund_code_registry import (
    FundRecord,
    ResolveResult,
    clear_cache,
    get_fund_list,
    is_trusted,
    resolve,
    score_match,
)


# ---------------------------------------------------------------------------
# 确定性测试数据（不触网）
# ---------------------------------------------------------------------------
TEST_FUNDS: list[FundRecord] = [
    FundRecord(code="005827", name="易方达蓝筹精选混合", type="混合型"),
    FundRecord(code="161725", name="招商中证白酒指数", type="指数型"),
    FundRecord(code="110011", name="易方达优质精选混合", type="混合型"),
    FundRecord(code="005876", name="易方达蓝筹精选混合C", type="混合型"),
]


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入确定性基金列表到 registry 缓存，用完清空。"""
    monkeypatch.setattr(registry, "_load_fund_list", lambda: TEST_FUNDS)
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# is_trusted（验收：可信代码 True / 臆测代码 False）
# ---------------------------------------------------------------------------
def test_is_trusted_returns_true_for_known_code(seeded: None) -> None:
    assert is_trusted("005827") is True
    assert is_trusted("161725") is True


def test_is_trusted_returns_false_for_fabricated_code(seeded: None) -> None:
    """臆测的 6 位代码不在可信集 -> False。"""
    assert is_trusted("999999") is False
    assert is_trusted("000000") is False


def test_is_trusted_rejects_non_six_digit(seeded: None) -> None:
    """非 6 位纯数字一律不可信。"""
    assert is_trusted("0058") is False
    assert is_trusted("0058270") is False
    assert is_trusted("abc123") is False
    assert is_trusted("") is False
    assert is_trusted("  005827  ") is True  # 去空白后是合法代码


# ---------------------------------------------------------------------------
# resolve：code 路径（命中 / 未命中）
# ---------------------------------------------------------------------------
def test_resolve_code_hit(seeded: None) -> None:
    r = resolve("005827")
    assert isinstance(r, ResolveResult)
    assert r.matched is True
    assert len(r.hits) == 1
    assert r.hits[0].code == "005827"
    assert r.hits[0].name == "易方达蓝筹精选混合"
    assert r.hits[0].type == "混合型"
    assert r.hits[0].score > 0


def test_resolve_code_miss(seeded: None) -> None:
    r = resolve("999999")
    assert r.matched is False
    assert r.hits == []


def test_resolve_code_strips_whitespace(seeded: None) -> None:
    r = resolve("  161725  ")
    assert r.matched is True
    assert r.hits[0].code == "161725"


# ---------------------------------------------------------------------------
# resolve：name 路径（命中 / 未命中）
# ---------------------------------------------------------------------------
def test_resolve_name_exact_hit(seeded: None) -> None:
    r = resolve("易方达蓝筹精选混合")
    assert r.matched is True
    codes = {h.code for h in r.hits}
    assert "005827" in codes


def test_resolve_name_fuzzy_hit(seeded: None) -> None:
    """包含匹配：简写名应命中全称基金。"""
    r = resolve("易方达蓝筹")
    assert r.matched is True
    codes = {h.code for h in r.hits}
    assert "005827" in codes
    # C 类也应被包含匹配拉进来
    assert "005876" in codes


def test_resolve_name_miss(seeded: None) -> None:
    r = resolve("完全不存在的基金名称XYZ")
    assert r.matched is False
    assert r.hits == []


def test_resolve_empty_input_returns_miss(seeded: None) -> None:
    assert resolve("").matched is False
    assert resolve("   ").matched is False


def test_resolve_respects_limit(seeded: None) -> None:
    """limit 截断返回数量。"""
    r = resolve("易方达", limit=1)
    assert len(r.hits) == 1


def test_resolve_result_carries_input(seeded: None) -> None:
    r = resolve("招商中证白酒")
    assert r.input == "招商中证白酒"
    assert r.matched is True
    assert r.hits[0].code == "161725"


# ---------------------------------------------------------------------------
# 缓存命中（验收：不每次打 akshare/网络）
# ---------------------------------------------------------------------------
def test_get_fund_list_caches_and_does_not_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _loader() -> list[FundRecord]:
        calls["n"] += 1
        return TEST_FUNDS

    monkeypatch.setattr(registry, "_load_fund_list", _loader)
    clear_cache()

    first = get_fund_list()
    assert calls["n"] == 1
    # 第二次应命中缓存，不再调 loader
    second = get_fund_list()
    assert calls["n"] == 1
    # 同一缓存对象
    assert first is second


def test_clear_cache_forces_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _loader() -> list[FundRecord]:
        calls["n"] += 1
        return TEST_FUNDS

    monkeypatch.setattr(registry, "_load_fund_list", _loader)
    clear_cache()

    get_fund_list()
    assert calls["n"] == 1
    clear_cache()
    get_fund_list()
    assert calls["n"] == 2


def test_empty_load_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """加载返回空时不缓存，下次重试（与原 runtime 行为一致）。"""
    calls = {"n": 0}

    def _loader() -> list[FundRecord]:
        calls["n"] += 1
        return []

    monkeypatch.setattr(registry, "_load_fund_list", _loader)
    clear_cache()

    assert get_fund_list() == []
    assert calls["n"] == 1
    assert get_fund_list() == []
    assert calls["n"] == 2  # 空结果未缓存，再次调用重新加载


# ---------------------------------------------------------------------------
# score_match：确定性打分（从原 runtime._score_match 抽出，行为不变）
# ---------------------------------------------------------------------------
def test_score_match_exact_returns_high() -> None:
    assert score_match("易方达蓝筹精选混合", "易方达蓝筹精选混合") >= 120.0


def test_score_match_unrelated_returns_zero() -> None:
    assert score_match("招商中证白酒", "易方达蓝筹精选混合") == 0.0


# ---------------------------------------------------------------------------
# fund_name_to_code/run 回归：抽 registry 后行为不变
# ---------------------------------------------------------------------------
def test_run_code_provided_unchanged(seeded: None) -> None:
    """用户已给 6 位代码 -> code_provided 模式（T3 不改此分支）。"""
    from agents.skills.fund_name_to_code.runtime import run

    out = json.loads(__import__("asyncio").run(run("帮我看下 005827", {})))
    assert out["ok"] is True
    assert out["mode"] == "code_provided"
    assert out["codes"] == ["005827"]


def test_run_name_to_code_uses_registry(seeded: None) -> None:
    """名称查询走 registry 的可信集，仍能命中。"""
    from agents.skills.fund_name_to_code.runtime import run

    out = json.loads(__import__("asyncio").run(run("易方达蓝筹精选", {})))
    assert out["ok"] is True
    assert out["mode"] == "name_to_code"
    codes = {m["code"] for m in out["matches"]}
    assert "005827" in codes


def test_run_no_match_returns_no_match(seeded: None) -> None:
    from agents.skills.fund_name_to_code.runtime import run

    out = json.loads(__import__("asyncio").run(run("完全不存在的基金XYZ", {})))
    assert out["ok"] is False
    assert out["mode"] == "no_match"
