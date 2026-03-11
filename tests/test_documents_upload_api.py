# T032：POST /api/v1/documents/upload 投递到 ingestion 队列
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


def test_documents_upload_returns_doc_id_or_503(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
        headers={"Authorization": "Bearer ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] in (0, 503)
    if body["code"] == 0:
        assert "doc_id" in body["data"] and body["data"]["doc_id"]
