# T030：POST /compare、/recommend、/report/generate 契约与编排调用
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


def test_compare_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/compare",
        json={"productIds": ["p1", "p2"]},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "trace-c"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "code" in body and "message" in body and "data" in body
    assert body["code"] in (0, 500)  # 0 成功；500 为 data_access/智能体未配置等
    if body["code"] == 0:
        data = body["data"]
        assert "comparisonTable" in data
        assert "summary" in data
        assert "citations" in data
        assert "trace" in data and "traceId" in data["trace"]


def test_compare_validation_fail(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/compare",
        json={"productIds": ["only_one"]},
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 40001  # 参数校验


def test_recommend_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/recommend",
        json={"customerProfile": "稳健型，期限 1 年", "topN": 3},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "trace-r"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "code" in body and "data" in body
    assert body["code"] in (0, 40001, 500)
    if body["code"] == 0:
        data = body["data"]
        assert "products" in data
        assert "disclaimers" in data
        assert "trace" in data


def test_recommend_validation_empty_profile(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/recommend",
        json={},
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 40001


def test_report_generate_ok(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/report/generate",
        json={"templateId": "周报", "timeRange": "本周", "topic": "市场解读"},
        headers={"Authorization": "Bearer ok", "X-Request-Id": "trace-report"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "code" in body and "data" in body
    assert body["code"] in (0, 500)
    if body["code"] == 0:
        data = body["data"]
        assert "reportBlocks" in data
        assert "citations" in data
        assert "trace" in data
