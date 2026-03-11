"""审计服务单元/集成测试：append_event、get_evidence、冷热分层、export_report。"""
import json
import pytest

from audit.types import AuditEvent, Evidence
from audit import (
    append_event,
    get_evidence,
    archive_to_cold,
    list_answer_ids_for_retention,
    export_report,
    RETENTION_MONTHS,
)


def test_retention_constant():
    assert RETENTION_MONTHS == 6


def test_audit_event_to_dict():
    ev = AuditEvent("compliance_result", {"action": "pass", "policy_version": "v1"})
    d = ev.to_dict()
    assert d["event_type"] == "compliance_result"
    assert d["payload"]["action"] == "pass"


def test_evidence_to_dict():
    from datetime import datetime
    ev = Evidence(
        answer_id="a1",
        session_id="s1",
        user_id="u1",
        intent="faq",
        events=[AuditEvent("request", {"query": "test"})],
    )
    d = ev.to_dict()
    assert d["answer_id"] == "a1"
    assert len(d["events"]) == 1
    assert d["events"][0]["event_type"] == "request"


def test_append_event_without_mysql():
    """MySQL 未配置时 append_event 返回 False。"""
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    ok = append_event("aid1", "request", {"query": "hello"}, session_id="s1", user_id="u1")
    assert ok is False


def test_get_evidence_without_mysql():
    """MySQL 未配置时 get_evidence 返回 None。"""
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    ev = get_evidence("aid1")
    assert ev is None


def test_export_report_without_mysql():
    """MySQL 未配置时 export_report 返回空列表。"""
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    report = export_report(limit=10)
    assert report == []


def test_list_answer_ids_for_retention_without_mysql():
    """MySQL 未配置时 list_answer_ids_for_retention 返回空列表。"""
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    ids = list_answer_ids_for_retention(older_than_days=180)
    assert ids == []


@pytest.mark.integration
def test_append_event_and_get_evidence_with_mysql():
    """MySQL 已配置时：append_event 落库后 get_evidence 可查。需先执行 004 迁移。"""
    from pkg.mysql_client import is_configured
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过集成测试")
    answer_id = "test-audit-answer-001"
    ok = append_event(
        answer_id,
        "request",
        {"query": "产品风险", "trace_id": "t1"},
        session_id="sess-1",
        user_id="user-1",
        intent="product_interpretation",
        model_version="qwen3",
        policy_version="v1",
    )
    assert ok is True
    ok2 = append_event(answer_id, "compliance_result", {"action": "pass", "policy_version": "v1"})
    assert ok2 is True
    ev = get_evidence(answer_id)
    assert ev is not None
    assert ev["answer_id"] == answer_id
    assert ev["session_id"] == "sess-1"
    assert ev["user_id"] == "user-1"
    assert ev["intent"] == "product_interpretation"
    assert len(ev["events"]) == 2
    types = {e["event_type"] for e in ev["events"]}
    assert "request" in types and "compliance_result" in types


@pytest.mark.integration
def test_export_report_with_mysql():
    """MySQL 已配置时：export_report 按 answer_id 可筛。"""
    from pkg.mysql_client import is_configured
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过集成测试")
    report = export_report(answer_ids=["test-audit-answer-001"], limit=10)
    # 可能为空（若上条测试未跑或 DB 干净），或至少一条
    assert isinstance(report, list)
    for item in report:
        assert "answer_id" in item and "events" in item
