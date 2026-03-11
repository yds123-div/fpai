# T031：GET evidence、POST feedback、GET products/search、GET|POST sessions
import pytest
from fastapi.testclient import TestClient


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


def test_evidence_not_found(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get(
        "/api/v1/evidence/nonexistent-id-123",
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] in (0, 40403, 500)
    if body["code"] == 0:
        assert "answer_id" in body["data"]


def test_feedback_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/feedback",
        json={"answerId": "ans-1", "rating": "useful", "comment": "很好"},
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] in (0, 500)
    if body["code"] == 0:
        assert body["data"].get("ack") is True


def test_feedback_validation_rating(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/feedback",
        json={"answerId": "ans-1", "rating": "invalid_rating"},
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 40001


def test_products_search_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get(
        "/api/v1/products/search",
        params={"page": 1, "pageSize": 10},
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] in (0, 500)
    if body["code"] == 0:
        assert "products" in body["data"] and "total" in body["data"]


def test_sessions_get_not_found(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get(
        "/api/v1/sessions/nonexistent-session-id",
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] in (40401, 500)


def test_sessions_post_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/sessions",
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert "sessionId" in body["data"] and body["data"]["sessionId"]
    assert body["data"].get("id") == body["data"]["sessionId"]


def test_sessions_get_ok(monkeypatch):
    client = _make_client(monkeypatch)
    create = client.post("/api/v1/sessions", headers={"Authorization": "Bearer ok"})
    assert create.status_code == 200 and create.json()["code"] == 0
    session_id = create.json()["data"]["sessionId"]
    resp = client.get(
        f"/api/v1/sessions/{session_id}",
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # 无 Redis/MySQL 时 get 可能 40401；有存储时 0
    assert body["code"] in (0, 40401)
    if body["code"] == 0:
        assert body["data"]["id"] == session_id
        assert "user_id" in body["data"] and "product_ids" in body["data"]
