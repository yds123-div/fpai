import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def test_append_message_looks_success_but_history_empty_when_mysql_unconfigured(monkeypatch):
    """
    RCA 回归测试：
    - 当 MySQL 未配置时，append_message 返回 True（调用方感知“成功”）
    - 但 get_recent_messages 固定返回 []（刷新后无法恢复历史）
    """
    from orchestrator import session as session_mod

    monkeypatch.setattr(session_mod, "mysql_configured", lambda: False, raising=True)
    monkeypatch.setattr(session_mod, "session_context_refresh", lambda *args, **kwargs: True, raising=True)

    ok = session_mod.append_message(
        session_id="sid_rca_001",
        role="assistant",
        content_summary="hello",
        answer_id="aid_rca_001",
    )
    assert ok is True

    rows = session_mod.get_recent_messages("sid_rca_001", limit=20)
    assert rows == []
