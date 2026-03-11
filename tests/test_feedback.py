"""反馈闭环单元/集成测试：submit_feedback、list_by_*、get_stats。"""
import pytest

from feedback.types import Rating, FeedbackRecord
from feedback import (
    submit_feedback,
    list_by_answer_id,
    list_by_user_id,
    get_stats,
)


def test_rating_enum():
    assert Rating.USEFUL.value == "useful"
    assert Rating.NOT_USEFUL.value == "not_useful"
    assert Rating.INACCURATE.value == "inaccurate"


def test_feedback_record_to_dict():
    from datetime import datetime
    rec = FeedbackRecord(
        id=1,
        answer_id="a1",
        user_id="u1",
        rating="useful",
        comment="很好",
        created_at=datetime(2025, 3, 1, 12, 0, 0),
    )
    d = rec.to_dict()
    assert d["answer_id"] == "a1"
    assert d["rating"] == "useful"
    assert d["comment"] == "很好"
    assert "2025-03-01" in (d["created_at"] or "")


def test_submit_feedback_invalid_rating():
    """无效 rating 或空参数时返回 False。"""
    assert submit_feedback("a1", "u1", "invalid_rating") is False
    assert submit_feedback("", "u1", "useful") is False
    assert submit_feedback("a1", "", "useful") is False
    assert submit_feedback("a1", "u1", "") is False


def test_submit_feedback_without_mysql():
    """MySQL 未配置时 submit_feedback 返回 False。"""
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    assert submit_feedback("a1", "u1", "useful", "comment") is False


def test_list_by_answer_id_without_mysql():
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    assert list_by_answer_id("a1") == []


def test_list_by_user_id_without_mysql():
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    assert list_by_user_id("u1") == []


def test_get_stats_without_mysql():
    from pkg.mysql_client import is_configured
    if is_configured():
        pytest.skip("MySQL 已配置，跳过无 DB 场景")
    s = get_stats()
    assert s["total"] == 0
    assert s["useful_rate"] == 0.0
    assert s["useful"] == 0


@pytest.mark.integration
def test_submit_and_list_with_mysql():
    """MySQL 已配置时：提交反馈后可按 answer_id / user_id 查询。"""
    from pkg.mysql_client import is_configured
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过集成测试")
    aid = "test-feedback-answer-001"
    uid = "test-feedback-user-001"
    ok = submit_feedback(aid, uid, "useful", "很有帮助")
    assert ok is True
    by_answer = list_by_answer_id(aid, limit=10)
    assert len(by_answer) >= 1
    assert by_answer[0]["answer_id"] == aid and by_answer[0]["user_id"] == uid
    assert by_answer[0]["rating"] == "useful"
    by_user = list_by_user_id(uid, limit=10)
    assert len(by_user) >= 1
    assert any(r["answer_id"] == aid for r in by_user)


@pytest.mark.integration
def test_get_stats_with_mysql():
    """MySQL 已配置时：get_stats 返回各 rating 数量与有用率。"""
    from pkg.mysql_client import is_configured
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过集成测试")
    s = get_stats()
    assert "useful" in s and "not_useful" in s and "inaccurate" in s
    assert s["total"] >= 0
    assert 0 <= s["useful_rate"] <= 1.0
