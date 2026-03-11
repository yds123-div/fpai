"""
Redis 键约定与封装，见 technical_design §4.2。

键约定：
- 会话上下文 session:{sessionId}，TTL 按会话超时（如 30 分钟续期）
- 产品热点缓存 product:summary:{productId}
- 检索结果缓存 retrieval:cache:{query_hash}:{filters_hash}:{user_context_hash}，TTL 5–10 分钟
- 限流 ratelimit:{userId}:chat
- 幂等 idempotent:{requestId}
"""
import hashlib
import json
import os
from typing import Any

from pkg.redis_client import get_client

# 键前缀（与 technical_design §4.2 一致）
SESSION_PREFIX = "session:"
PRODUCT_SUMMARY_PREFIX = "product:summary:"
RETRIEVAL_CACHE_PREFIX = "retrieval:cache:"
RATELIMIT_PREFIX = "ratelimit:"
IDEMPOTENT_PREFIX = "idempotent:"

# 默认 TTL（秒），可从环境覆盖
DEFAULT_SESSION_TTL = int(os.getenv("REDIS_SESSION_TTL_SECONDS", "1800"))  # 30 min
DEFAULT_PRODUCT_CACHE_TTL = int(os.getenv("REDIS_PRODUCT_CACHE_TTL_SECONDS", "600"))  # 10 min
DEFAULT_RETRIEVAL_CACHE_TTL = int(os.getenv("REDIS_RETRIEVAL_CACHE_TTL_SECONDS", "600"))  # 5–10 min
DEFAULT_RATELIMIT_WINDOW = int(os.getenv("REDIS_RATELIMIT_WINDOW_SECONDS", "60"))  # 1 min
DEFAULT_RATELIMIT_MAX = int(os.getenv("REDIS_RATELIMIT_CHAT_MAX", "60"))  # 每分钟上限
DEFAULT_IDEMPOTENT_TTL = int(os.getenv("REDIS_IDEMPOTENT_TTL_SECONDS", "300"))  # 5 min


def key_session(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def key_product_summary(product_id: str) -> str:
    return f"{PRODUCT_SUMMARY_PREFIX}{product_id}"


def key_retrieval_cache(query_hash: str, filters_hash: str, user_context_hash: str) -> str:
    """检索结果缓存 key；三部分 hash 可分别传入或由调用方拼接。"""
    combined = f"{query_hash}:{filters_hash}:{user_context_hash}"
    return f"{RETRIEVAL_CACHE_PREFIX}{combined}"


def key_retrieval_cache_hashed(query_hash: str, filters_hash: str, user_context_hash: str) -> str:
    """检索缓存 key 过长时可用单 hash 缩短。"""
    h = hashlib.sha256(f"{query_hash}:{filters_hash}:{user_context_hash}".encode()).hexdigest()[:32]
    return f"{RETRIEVAL_CACHE_PREFIX}{h}"


def key_ratelimit(user_id: str, scope: str = "chat") -> str:
    return f"{RATELIMIT_PREFIX}{user_id}:{scope}"


def key_idempotent(request_id: str) -> str:
    return f"{IDEMPOTENT_PREFIX}{request_id}"


def _encode(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _decode(data: bytes | None) -> Any:
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return data.decode("utf-8", errors="replace")


# ---------- 会话上下文 ----------


def session_context_get(session_id: str) -> Any | None:
    """获取会话上下文（JSON 或字符串）；无或 Redis 不可用时返回 None。"""
    client = get_client()
    if not client:
        return None
    key = key_session(session_id)
    data = client.get(key)
    return _decode(data)


def session_context_set(session_id: str, value: Any, ttl_seconds: int | None = None) -> bool:
    """设置会话上下文；ttl 默认 REDIS_SESSION_TTL_SECONDS。"""
    client = get_client()
    if not client:
        return False
    key = key_session(session_id)
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_SESSION_TTL
    client.setex(key, ttl, _encode(value))
    return True


def session_context_delete(session_id: str) -> bool:
    client = get_client()
    if not client:
        return False
    client.delete(key_session(session_id))
    return True


def session_context_ttl(session_id: str) -> int:
    """剩余 TTL（秒），-2 表示 key 不存在，-1 表示无过期。"""
    client = get_client()
    if not client:
        return -2
    return client.ttl(key_session(session_id))


def session_context_refresh(session_id: str, ttl_seconds: int | None = None) -> bool:
    """续期会话 TTL。"""
    client = get_client()
    if not client:
        return False
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_SESSION_TTL
    return bool(client.expire(key_session(session_id), ttl))


# ---------- 产品热点缓存 ----------


def product_summary_get(product_id: str) -> Any | None:
    client = get_client()
    if not client:
        return None
    return _decode(client.get(key_product_summary(product_id)))


def product_summary_set(
    product_id: str, value: Any, ttl_seconds: int | None = None
) -> bool:
    client = get_client()
    if not client:
        return False
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_PRODUCT_CACHE_TTL
    client.setex(key_product_summary(product_id), ttl, _encode(value))
    return True


def product_summary_delete(product_id: str) -> bool:
    client = get_client()
    if not client:
        return False
    client.delete(key_product_summary(product_id))
    return True


# ---------- 检索结果缓存 ----------


def retrieval_cache_get(query_hash: str, filters_hash: str, user_context_hash: str) -> Any | None:
    """使用 key_retrieval_cache_hashed 缩短 key 长度。"""
    client = get_client()
    if not client:
        return None
    key = key_retrieval_cache_hashed(query_hash, filters_hash, user_context_hash)
    return _decode(client.get(key))


def retrieval_cache_set(
    query_hash: str,
    filters_hash: str,
    user_context_hash: str,
    value: Any,
    ttl_seconds: int | None = None,
) -> bool:
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_RETRIEVAL_CACHE_TTL
    client = get_client()
    if not client:
        return False
    key = key_retrieval_cache_hashed(query_hash, filters_hash, user_context_hash)
    client.setex(key, ttl, _encode(value))
    return True


# ---------- 限流 ratelimit:{userId}:chat ----------


def ratelimit_check(user_id: str, scope: str = "chat") -> tuple[bool, int]:
    """
    检查是否超限。返回 (是否允许, 当前计数)。
    使用固定窗口：key 带窗口起始时间或单窗口内 INCR，首次设置 EXPIRE。
    """
    client = get_client()
    if not client:
        return True, 0
    key = key_ratelimit(user_id, scope)
    try:
        count = client.get(key)
        n = int(count) if count else 0
    except (ValueError, TypeError):
        n = 0
    return n < DEFAULT_RATELIMIT_MAX, n


def ratelimit_incr(user_id: str, scope: str = "chat") -> tuple[bool, int]:
    """
    增加计数并返回 (是否允许, 当前计数)。首次 incr 时设置窗口 TTL。
    """
    client = get_client()
    if not client:
        return True, 0
    key = key_ratelimit(user_id, scope)
    pipe = client.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    results = pipe.execute()
    n = results[0]
    ttl = results[1]
    if ttl <= 0:
        client.expire(key, DEFAULT_RATELIMIT_WINDOW)
    return n <= DEFAULT_RATELIMIT_MAX, int(n)


# ---------- 幂等 idempotent:{requestId} ----------


def idempotent_set_if_not_exists(
    request_id: str, value: Any = "1", ttl_seconds: int | None = None
) -> bool:
    """
    若 requestId 尚未存在则设置并返回 True，否则返回 False（已存在，幂等命中）。
    """
    client = get_client()
    if not client:
        return True
    key = key_idempotent(request_id)
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_IDEMPOTENT_TTL
    ok = client.set(key, _encode(value), nx=True, ex=ttl)
    return bool(ok)


def idempotent_get(request_id: str) -> Any | None:
    """获取幂等键对应值；不存在返回 None。"""
    client = get_client()
    if not client:
        return None
    return _decode(client.get(key_idempotent(request_id)))
