"""合规服务单元测试：check_input、check_output、策略与黑白名单、决策类型。"""
import json
import pytest

from compliance.types import ComplianceAction, ComplianceDecision
from compliance.config import CompliancePolicy, DEFAULT_POLICY
from compliance import service as compliance_service


# ---------- 类型与配置 ----------


def test_compliance_decision_is_allowed():
    """PASS 与 SUPPLEMENT_PROMPT 为允许，REJECT/REWRITE 为不允许。"""
    assert ComplianceDecision(ComplianceAction.PASS).is_allowed() is True
    assert ComplianceDecision(ComplianceAction.SUPPLEMENT_PROMPT).is_allowed() is True
    assert ComplianceDecision(ComplianceAction.REJECT).is_allowed() is False
    assert ComplianceDecision(ComplianceAction.REWRITE).is_allowed() is False


def test_compliance_decision_to_dict():
    """to_dict 包含 action、reason、suggestion、policy_version；改写/补充时含对应字段。"""
    d = ComplianceDecision(
        ComplianceAction.REJECT,
        reason="命中黑名单",
        suggestion="建议转人工",
        policy_version="v1",
    ).to_dict()
    assert d["action"] == "reject"
    assert d["reason"] == "命中黑名单"
    assert d["suggestion"] == "建议转人工"
    assert d["policy_version"] == "v1"
    d2 = ComplianceDecision(
        ComplianceAction.REWRITE,
        rewritten_text="改写后内容",
        policy_version="v1",
    ).to_dict()
    assert d2.get("rewritten_text") == "改写后内容"
    d3 = ComplianceDecision(
        ComplianceAction.SUPPLEMENT_PROMPT,
        supplement_prompt="投资有风险",
        policy_version="v1",
    ).to_dict()
    assert d3.get("supplement_prompt") == "投资有风险"


def test_compliance_policy_from_dict():
    """CompliancePolicy.from_dict 从 config 返回的 dict 构造（T014 MySQL 加载）。"""
    raw = {
        "policy_version": "v1.2",
        "blacklist_keywords": ["保本保息", "承诺收益"],
        "whitelist_keywords": ["历史收益仅供参考"],
        "enable_llm_input_check": True,
        "enable_llm_output_check": False,
    }
    policy = CompliancePolicy.from_dict(raw)
    assert policy.policy_version == "v1.2"
    assert policy.blacklist_matches("保本保息") == ["保本保息"]
    assert policy.is_whitelisted("历史收益仅供参考") is True
    assert policy.enable_llm_output_check is False


def test_policy_blacklist_matches():
    """黑名单命中返回词列表，未命中返回空。"""
    policy = CompliancePolicy(blacklist_keywords=["保本保息", "承诺收益"], policy_version="v1")
    assert policy.blacklist_matches("这款产品保本保息") == ["保本保息"]
    assert policy.blacklist_matches("承诺收益很高") == ["承诺收益"]
    assert policy.blacklist_matches("普通理财产品介绍") == []
    assert policy.blacklist_matches("") == []


def test_policy_whitelist():
    """白名单短语存在时视为放行（用于减少误拦）。"""
    policy = CompliancePolicy(
        blacklist_keywords=["收益"],
        whitelist_keywords=["历史收益仅供参考"],
        policy_version="v1",
    )
    # 仅“收益”命中黑名单，但若整句含白名单可配置为放行（此处仅测 is_whitelisted 行为）
    assert policy.is_whitelisted("历史收益仅供参考") is True
    assert policy.is_whitelisted("承诺收益") is False


# ---------- check_input ----------


def test_check_input_empty():
    """空输入直接通过。"""
    r = compliance_service.check_input("", policy=DEFAULT_POLICY)
    assert r.action == ComplianceAction.PASS


def test_check_input_blacklist_reject():
    """输入命中黑名单且无白名单则拒答。"""
    policy = CompliancePolicy(
        blacklist_keywords=["保本保息", "承诺收益"],
        enable_llm_input_check=False,
        policy_version="v1",
    )
    r = compliance_service.check_input("这个产品保本保息吗", policy=policy)
    assert r.action == ComplianceAction.REJECT
    assert "保本保息" in r.reason
    assert r.suggestion


def test_check_input_pass_when_no_hit():
    """未命中黑名单且不调用 LLM 时通过。"""
    policy = CompliancePolicy(
        blacklist_keywords=["违规词"],
        enable_llm_input_check=False,
        policy_version="v1",
    )
    r = compliance_service.check_input("请介绍下这款理财", policy=policy)
    assert r.action == ComplianceAction.PASS


def test_check_input_whitelist_bypass():
    """白名单短语存在时可不触发黑名单拒答（当前实现：黑名单命中即拒答，白名单仅用于 is_whitelisted 查询；若需白名单优先可在 service 中先判白名单）。"""
    # 当前 service 逻辑：先判黑名单命中 -> 再判是否白名单；若白名单命中则不再拒答
    policy = CompliancePolicy(
        blacklist_keywords=["收益"],
        whitelist_keywords=["历史收益仅供参考"],
        enable_llm_input_check=False,
        policy_version="v1",
    )
    # “历史收益仅供参考” 既含“收益”又含白名单；我们在 service 里是 hits and not is_whitelisted，所以白名单会放行
    r = compliance_service.check_input("历史收益仅供参考，不预示未来", policy=policy)
    assert r.action == ComplianceAction.PASS


# ---------- check_output ----------


def test_check_output_empty():
    """无输出内容时通过。"""
    r = compliance_service.check_output("", policy=DEFAULT_POLICY)
    assert r.action == ComplianceAction.PASS


def test_check_output_blacklist_reject():
    """输出命中黑名单则拒答。"""
    policy = CompliancePolicy(
        blacklist_keywords=["稳赚不赔"],
        enable_llm_output_check=False,
        policy_version="v1",
    )
    r = compliance_service.check_output("该产品稳赚不赔，请放心购买", policy=policy)
    assert r.action == ComplianceAction.REJECT
    assert "稳赚不赔" in r.reason


def test_check_output_pass_when_no_hit():
    """未命中黑名单且不调用 LLM 时通过。"""
    policy = CompliancePolicy(
        blacklist_keywords=["违规词"],
        enable_llm_output_check=False,
        policy_version="v1",
    )
    r = compliance_service.check_output("本产品为净值型，历史业绩不预示未来表现。", policy=policy)
    assert r.action == ComplianceAction.PASS


# ---------- _parse_llm_decision ----------


def test_parse_llm_decision_valid():
    """解析合法 JSON 得到对应决策。"""
    raw = json.dumps({
        "action": "reject",
        "reason": "承诺收益",
        "suggestion": "建议转人工",
    })
    r = compliance_service._parse_llm_decision(raw, "v1", default_action=ComplianceAction.PASS)
    assert r.action == ComplianceAction.REJECT
    assert r.reason == "承诺收益"
    assert r.suggestion == "建议转人工"


def test_parse_llm_decision_rewrite_and_supplement():
    """解析 rewrite / supplement_prompt 含 rewritten_text、supplement_prompt。"""
    raw = json.dumps({
        "action": "supplement_prompt",
        "reason": "需加风险提示",
        "suggestion": "请补充说明",
        "supplement_prompt": "投资有风险，过往业绩不预示未来。",
    })
    r = compliance_service._parse_llm_decision(
        raw, "v1", default_action=ComplianceAction.PASS, allow_rewrite=True
    )
    assert r.action == ComplianceAction.SUPPLEMENT_PROMPT
    assert r.supplement_prompt == "投资有风险，过往业绩不预示未来。"


def test_parse_llm_decision_invalid_json_fallback():
    """LLM 返回非 JSON 时降级为通过。"""
    r = compliance_service._parse_llm_decision("not json at all", "v1")
    assert r.action == ComplianceAction.PASS
    assert "格式异常" in r.reason
