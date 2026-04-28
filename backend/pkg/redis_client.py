"""
Redis 客户端封装，供会话上下文、缓存、限流、幂等等模块复用。

支持从 REDIS_URL 解析或从 REDIS_HOST/PORT/PASSWORD/DB 构建；
使用连接池（ConnectionPool）以适配并发。未配置时 get_client() 返回 None。
"""
import os
import time
import logging
from typing import Any

try:
    import redis
except ImportError:
    redis = None  # type: ignore[assignment]

_redis_pool: "redis.ConnectionPool | None" = None
_redis_client: "redis.Redis[bytes] | None" = None
_redis_unavailable_until_monotonic: float = 0.0
_last_skip_log_monotonic: float = 0.0

# 连接池大小，可从环境覆盖
DEFAULT_POOL_MAX_CONNECTIONS = 20
DEFAULT_CONNECT_TIMEOUT_SECONDS = 0.2
DEFAULT_IO_TIMEOUT_SECONDS = 0.2
DEFAULT_FAILFAST_COOLDOWN_SECONDS = 30.0
DEFAULT_SKIP_LOG_INTERVAL_SECONDS = 5.0

logger = logging.getLogger(__name__)


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
    connect_timeout = float(os.getenv("REDIS_CONNECT_TIMEOUT_SECONDS", str(DEFAULT_CONNECT_TIMEOUT_SECONDS)))
    io_timeout = float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", str(DEFAULT_IO_TIMEOUT_SECONDS)))
    _redis_pool = redis.ConnectionPool.from_url(
        _redis_url(),
        max_connections=max_connections,
        decode_responses=False,
        socket_connect_timeout=max(0.05, connect_timeout),
        socket_timeout=max(0.05, io_timeout),
    )
    return _redis_pool


def get_client(op_name: str | None = None) -> "redis.Redis[bytes] | None":
    """
    返回基于连接池的单例 Redis 客户端；
    若 redis 未安装或连接池创建/探测失败则返回 None。
    """
    global _redis_client, _redis_unavailable_until_monotonic, _last_skip_log_monotonic
    if redis is None:
        return None
    now = time.perf_counter()
    if now < _redis_unavailable_until_monotonic:
        # 冷却期内直接降级，避免每次请求都阻塞在连接超时。
        if now - _last_skip_log_monotonic >= DEFAULT_SKIP_LOG_INTERVAL_SECONDS:
            _last_skip_log_monotonic = now
            logger.warning(
                "[REDIS_DEGRADE] enabled=true reason=cooldown op=%s skip_connect=true remaining_ms=%d",
                op_name or "unknown",
                int((_redis_unavailable_until_monotonic - now) * 1000),
            )
        return None
    pool = _get_pool()
    if pool is None:
        return None
    if _redis_client is not None:
        return _redis_client
    started = time.perf_counter()
    try:
        _redis_client = redis.Redis(connection_pool=pool)
        _redis_client.ping()
        _redis_unavailable_until_monotonic = 0.0
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cooldown_s = float(os.getenv("REDIS_FAILFAST_COOLDOWN_SECONDS", str(DEFAULT_FAILFAST_COOLDOWN_SECONDS)))
        _redis_unavailable_until_monotonic = time.perf_counter() + max(1.0, cooldown_s)
        logger.warning(
            "[REDIS_DEGRADE] enabled=true reason=connect_failed op=%s elapsed_ms=%d skip_step=true cooldown_ms=%d",
            op_name or "unknown",
            elapsed_ms,
            int(max(1.0, cooldown_s) * 1000),
        )
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
