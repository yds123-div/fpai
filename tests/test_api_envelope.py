"""API 层：中间件 X-Request-Id、envelope 错误响应."""
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_response_has_x_request_id(client):
    """响应头应包含 X-Request-Id（中间件注入或沿用请求头）。"""
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-Request-Id" in r.headers
    assert len(r.headers["X-Request-Id"]) > 0


def test_x_request_id_echoed_from_request(client):
    """请求带 X-Request-Id 时，响应头应回传同一值。"""
    req_id = "my-trace-123"
    r = client.get("/health", headers={"X-Request-Id": req_id})
    assert r.headers.get("X-Request-Id") == req_id


def test_404_returns_envelope(client):
    """不存在的路径应返回统一 envelope（code=404）。"""
    r = client.get("/api/v1/nonexistent")
    assert r.status_code == 200
    body = r.json()
    assert "code" in body and "message" in body and "data" in body
    assert body["code"] == 404
