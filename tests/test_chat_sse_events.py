import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")


def _make_client(monkeypatch) -> TestClient:
    from api import middleware as api_middleware

    def _fake_verify_token(token: str):
        if token == "ok":
            return {"sub": "u_test", "role": "tester", "product_pool_ids": ["pool1"]}
        return None

    monkeypatch.setattr(api_middleware, "verify_token", _fake_verify_token, raising=True)

    from api.main import app

    return TestClient(app)


def _collect_sse_events(resp) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    cur_event = ""
    cur_data = ""
    for line in resp.iter_lines():
        if line is None:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")
        if line.startswith("event:"):
            cur_event = line[6:].strip()
            continue
        if line.startswith("data:"):
            cur_data = line[5:].strip()
            continue
        if line == "" and cur_event and cur_data:
            events.append((cur_event, json.loads(cur_data)))
            if cur_event == "done":
                break
            cur_event = ""
            cur_data = ""
    return events


def test_sse_event_order_with_structured_update(monkeypatch):
    client = _make_client(monkeypatch)
    from api.routes import chat as chat_route

    async def _fake_run_chat_turn_async(*args, **kwargs):
        stream_cb = kwargs.get("stream_callback")
        if callable(stream_cb):
            await stream_cb("分段1")
            await stream_cb("分段2")
        return SimpleNamespace(
            answer_id=kwargs.get("answer_id") or "aid-test",
            answer_blocks=["分段1分段2"],
            citations=[],
            compliance={},
            trace={"traceId": "tid"},
            suggested_questions=[],
            structured_outputs=[{"type": "fund_analysis", "mode": "single", "cards": [], "sections": [], "charts": [], "text": "ok"}],
        )

    monkeypatch.setattr(chat_route, "run_chat_turn_async", _fake_run_chat_turn_async, raising=True)

    with client.stream(
        "POST",
        "/api/v1/chat",
        json={"message": "你好", "stream": True},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "rid-sse-order"},
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    names = [name for name, _ in events]
    assert "message_start" in names
    assert "message_delta" in names
    assert "structured_update" in names
    assert "done" in names

    idx_start = names.index("message_start")
    idx_delta = names.index("message_delta")
    idx_struct = names.index("structured_update")
    idx_done = names.index("done")
    assert idx_start < idx_delta < idx_struct < idx_done


def test_done_fallback_emits_message_delta_and_keeps_structured_outputs(monkeypatch):
    client = _make_client(monkeypatch)
    from api.routes import chat as chat_route

    async def _fake_run_chat_turn_async(*args, **kwargs):
        return SimpleNamespace(
            answer_id=kwargs.get("answer_id") or "aid-fallback",
            answer_blocks=["没有流式token，走done兜底"],
            citations=[],
            compliance={},
            trace={"traceId": "tid2"},
            suggested_questions=[],
            structured_outputs=[{"type": "fund_analysis", "mode": "single", "cards": [], "sections": [], "charts": [], "text": "fallback"}],
        )

    monkeypatch.setattr(chat_route, "run_chat_turn_async", _fake_run_chat_turn_async, raising=True)

    with client.stream(
        "POST",
        "/api/v1/chat",
        json={"message": "你好", "stream": True},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "rid-sse-fallback"},
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    names = [name for name, _ in events]
    assert "message_start" in names
    assert "message_delta" in names
    assert "done" in names

    done_payload = next(payload for name, payload in events if name == "done")
    assert isinstance(done_payload.get("structuredOutputs"), list)
    assert done_payload["structuredOutputs"][0]["type"] == "fund_analysis"
