import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch):
    # 仅用于测试环境：确保 verify_token 可被调用（即使我们会 monkeypatch）。
    monkeypatch.setenv("JWT_SECRET", "test-secret")


def _make_client(monkeypatch) -> TestClient:
    # 鉴权中间件直接引用了 api.middleware.verify_token，这里 monkeypatch 让测试无需真实 JWT。
    from api import middleware as api_middleware

    def _fake_verify_token(token: str):
        if token == "ok":
            return {"sub": "u_test", "role": "tester", "product_pool_ids": ["pool1"]}
        return None

    monkeypatch.setattr(api_middleware, "verify_token", _fake_verify_token, raising=True)

    from api.main import app

    return TestClient(app)


def test_chat_non_stream_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/chat",
        json={"message": "你好", "stream": False},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "rid-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["sessionId"]
    assert body["data"]["answerId"]
    assert isinstance(body["data"]["answerBlocks"], list)
    assert "trace" in body["data"]
    assert body["data"]["trace"].get("traceId")


def test_chat_stream_sse(monkeypatch):
    client = _make_client(monkeypatch)
    with client.stream(
        "POST",
        "/api/v1/chat",
        json={"message": "你好", "stream": True},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "rid-2"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        # 读取一小段，至少应包含 done 或 message 事件
        chunk = next(resp.iter_text())
        assert "event:" in chunk

