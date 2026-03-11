"""pkg.redis_keys 单元测试：键约定与封装（无 Redis 时行为 + key 构建）."""
import pytest

from pkg.redis_keys import (
    key_idempotent,
    key_product_summary,
    key_ratelimit,
    key_retrieval_cache_hashed,
    key_session,
    idempotent_get,
    idempotent_set_if_not_exists,
    product_summary_get,
    ratelimit_check,
    ratelimit_incr,
    retrieval_cache_get,
    session_context_get,
    session_context_set,
)


@pytest.fixture(autouse=True)
def _redis_unavailable(monkeypatch):
    """使 redis_keys 内 get_client() 返回 None，避免依赖真实 Redis。"""
    monkeypatch.setattr("pkg.redis_keys.get_client", lambda: None)


def test_key_builders():
    assert key_session("s1") == "session:s1"
    assert key_product_summary("p1") == "product:summary:p1"
    assert key_ratelimit("u1", "chat") == "ratelimit:u1:chat"
    assert key_idempotent("req-1") == "idempotent:req-1"
    k = key_retrieval_cache_hashed("q", "f", "u")
    assert k.startswith("retrieval:cache:") and len(k) == len("retrieval:cache:") + 32


def test_session_context_no_redis():
    """无 Redis 时 get 返回 None，set 返回 False。"""
    assert session_context_get("any") is None
    assert session_context_set("any", {"x": 1}) is False


def test_product_summary_no_redis():
    assert product_summary_get("p1") is None


def test_retrieval_cache_no_redis():
    assert retrieval_cache_get("q", "f", "u") is None


def test_ratelimit_no_redis():
    """无 Redis 时不限流：允许，计数 0。"""
    allowed, n = ratelimit_check("u1")
    assert allowed is True
    assert n == 0
    allowed2, n2 = ratelimit_incr("u1")
    assert allowed2 is True
    assert n2 == 0


def test_idempotent_no_redis():
    """无 Redis 时 set_if_not_exists 返回 True（不阻塞），get 返回 None。"""
    assert idempotent_set_if_not_exists("req-no-redis") is True
    assert idempotent_get("req-no-redis") is None
