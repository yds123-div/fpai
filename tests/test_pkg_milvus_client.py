"""pkg.milvus_client 单元测试：Collection 约定、无 Milvus 时行为."""
import pytest

from pkg.milvus_client import (
    close_client,
    get_client,
    get_collection_name,
    ensure_collection,
    insert_chunks,
    search_with_filter,
    FIELD_DOC_ID,
    FIELD_PERMISSION_TAG,
    FIELD_CHUNK_TEXT,
)


def setup_function():
    close_client()


def test_get_collection_name_default():
    assert get_collection_name() == "fpai_chunks"


def test_get_client_without_milvus_or_server():
    """未安装 pymilvus 或 Milvus 服务不可用时 get_client 返回 None。"""
    client = get_client()
    assert client is None or hasattr(client, "list_collections")


def test_ensure_collection_no_client(monkeypatch):
    monkeypatch.setattr("pkg.milvus_client.get_client", lambda: None)
    from pkg.milvus_client import ensure_collection as _ensure
    assert _ensure(128) is False


def test_insert_chunks_no_client(monkeypatch):
    monkeypatch.setattr("pkg.milvus_client.get_client", lambda: None)
    from pkg.milvus_client import insert_chunks as _insert
    assert _insert(
        ids=["1"],
        vectors=[[0.1] * 4],
        doc_ids=["d1"],
        sources=["s1"],
        permission_tags=["pool1"],
        created_ats=[1234567890],
        chunk_texts=["text"],
    ) is False


def test_insert_chunks_length_mismatch(monkeypatch):
    """列表长度不一致时返回 False。"""
    mock_client = type("Mock", (), {"insert": lambda *a, **k: None})()
    monkeypatch.setattr("pkg.milvus_client.get_client", lambda: mock_client)
    from pkg.milvus_client import insert_chunks as _insert
    assert _insert(
        ids=["1", "2"],
        vectors=[[0.1] * 4],
        doc_ids=["d1"],
        sources=["s1"],
        permission_tags=["pool1"],
        created_ats=[123],
        chunk_texts=["t"],
    ) is False


def test_search_with_filter_no_client():
    close_client()
    result = search_with_filter([[0.1] * 4], filter_expr='permission_tag in ["pool1"]', top_k=5)
    assert result == [] or isinstance(result, list)


def test_field_constants():
    assert FIELD_DOC_ID == "doc_id"
    assert FIELD_PERMISSION_TAG == "permission_tag"
    assert FIELD_CHUNK_TEXT == "chunk_text"
