"""
Redis 客户端封装，供会话上下文、缓存、限流、幂等等模块复用。

支持从 REDIS_URL 解析或从 REDIS_HOST/PORT/PASSWORD/DB 构建；
使用连接池（ConnectionPool）以适配并发。未配置时 get_client() 返回 None。
"""
import os
from typing import Any

try:
    import redis
except ImportError:
    redis = None  # type: ignore[assignment]

_redis_pool: "redis.ConnectionPool | None" = None
_redis_client: "redis.Redis[bytes] | None" = None

# 连接池大小，可从环境覆盖
DEFAULT_POOL_MAX_CONNECTIONS = 20


def _redis_url() -> str:
    """优先使用 REDIS_URL，否则从各环境变量拼接。"""
    url = os.getenv("REDIS_URL", "").strip()
    if url:
        return url
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "") or None
    db = os.getenv("REDIS_DB", "0")
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def _get_pool() -> "redis.ConnectionPool | None":
    """获取或创建单例连接池。"""
    global _redis_pool
    if redis is None:
        return None
    if _redis_pool is not None:
        return _redis_pool
    try:
        max_connections = int(os.getenv("REDIS_POOL_MAX_CONNECTIONS", str(DEFAULT_POOL_MAX_CONNECTIONS)))
    except ValueError:
        max_connections = DEFAULT_POOL_MAX_CONNECTIONS
    _redis_pool = redis.ConnectionPool.from_url(
        _redis_url(),
        max_connections=max_connections,
        decode_responses=False,
        socket_connect_timeout=5,
    )
    return _redis_pool


def get_client() -> "redis.Redis[bytes] | None":
    """
    返回基于连接池的单例 Redis 客户端；
    若 redis 未安装或连接池创建/探测失败则返回 None。
    """
    global _redis_client
    if redis is None:
        return None
    pool = _get_pool()
    if pool is None:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis(connection_pool=pool)
        _redis_client.ping()
    except Exception:
        _redis_client = None
    return _redis_client


def close_client() -> None:
    """关闭全局 Redis 客户端与连接池，用于进程退出或测试清理。"""
    global _redis_client, _redis_pool
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
    if _redis_pool is not None:
        try:
            _redis_pool.disconnect()
        except Exception:
            pass
        _redis_pool = None


def is_available() -> bool:
    """检查 Redis 是否可用（已安装且连接成功）。"""
    return get_client() is not None
