"""pkg.minio_client 单元测试：Bucket 约定、路径规范、未配置时行为."""
import pytest

from pkg.minio_client import (
    build_object_name,
    get_bucket_audit,
    get_bucket_docs,
    get_client,
    is_configured,
    close_client,
)


def test_build_object_name():
    """路径规范 tenant/type/year-month/doc_id。"""
    name = build_object_name("t1", "raw", "2025-03", "doc-001")
    assert name == "t1/raw/2025-03/doc-001"
    name2 = build_object_name(" tenant ", " audit ", " 2025-01 ", " id ")
    assert name2 == "tenant/audit/2025-01/id"


def test_bucket_names_from_env_default():
    assert get_bucket_docs() == "fpai-docs"
    assert get_bucket_audit() == "fpai-audit"


def test_is_configured_without_key(monkeypatch):
    """未设置 MINIO_ACCESS_KEY 时 is_configured 为 False。"""
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    from pkg.minio_client import is_configured as _is_configured
    assert _is_configured() is False


def test_get_client_returns_none_or_client():
    """未配置或 minio 未安装时 get_client 返回 None；否则返回具 put_object 的客户端。"""
    close_client()
    client = get_client()
    assert client is None or hasattr(client, "put_object")
