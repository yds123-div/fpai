"""
MySQL 连接/会话封装，供会话、消息、配置、FAQ、反馈、审计等模块复用。

从环境变量读取：MYSQL_HOST、MYSQL_PORT、MYSQL_USER、MYSQL_PASSWORD、MYSQL_DATABASE；
可选 MYSQL_POOL_SIZE（>0 时启用连接池）以适配并发。
提供 get_connection() 与会话上下文管理器，事务内 commit/rollback。
"""
import os
import threading
from contextlib import contextmanager
from typing import Any, Generator

try:
    import pymysql
    from pymysql.connections import Connection
except ImportError:
    pymysql = None  # type: ignore[assignment]
    Connection = Any  # type: ignore[misc, assignment]

# 连接池默认最大连接数，0 表示不使用池（每次新建连接）
DEFAULT_POOL_SIZE = 0


def _connection_params() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", ""),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "fpai"),
        "charset": "utf8mb4",
    }


def _pool_size() -> int:
    try:
        return max(0, int(os.getenv("MYSQL_POOL_SIZE", str(DEFAULT_POOL_SIZE))))
    except ValueError:
        return DEFAULT_POOL_SIZE


class _ConnectionPool:
    """简单线程安全连接池：空闲队列 + 在用集合，不超过 max_size。"""

    def __init__(self, max_size: int, connect_params: dict[str, Any]) -> None:
        self._max_size = max_size
        self._params = connect_params
        self._idle: list[Any] = []
        self._in_use: set[Any] = set()
        self._lock = threading.Condition(threading.Lock())

    def _new_conn(self) -> Any:
        return pymysql.connect(**self._params)

    def get(self) -> Any:
        with self._lock:
            while True:
                if self._idle:
                    conn = self._idle.pop()
                    try:
                        conn.ping(reconnect=True)
                    except Exception:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        continue
                    self._in_use.add(conn)
                    return conn
                if len(self._in_use) + len(self._idle) < self._max_size:
                    conn = self._new_conn()
                    self._in_use.add(conn)
                    return conn
                self._lock.wait()

    def release(self, conn: Any, healthy: bool = True) -> None:
        with self._lock:
            self._in_use.discard(conn)
            if healthy:
                self._idle.append(conn)
                self._lock.notify()
            else:
                try:
                    conn.close()
                except Exception:
                    pass


_pool: _ConnectionPool | None = None


def _get_pool() -> _ConnectionPool | None:
    global _pool
    if pymysql is None or not _connection_params().get("user"):
        return None
    if _pool is None:
        size = _pool_size()
        if size <= 0:
            return None
        _pool = _ConnectionPool(size, _connection_params())
    return _pool


def is_configured() -> bool:
    """是否已配置 MySQL（至少填写了 user）。"""
    return bool(os.getenv("MYSQL_USER"))


@contextmanager
def _connection_impl(**kwargs: Any) -> Generator["Connection | None", None, None]:
    """内部：按是否启用池分别返回连接。"""
    if pymysql is None:
        yield None
        return
    params = _connection_params()
    params.update(kwargs)
    if not params["user"]:
        yield None
        return
    pool = _get_pool()
    if pool is None:
        conn = None
        try:
            conn = pymysql.connect(**params)
            yield conn
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
        return
    conn = None
    healthy = True
    try:
        conn = pool.get()
        yield conn
        conn.commit()
    except Exception:
        healthy = False
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            pool.release(conn, healthy=healthy)


@contextmanager
def get_connection(**kwargs: Any) -> Generator["Connection | None", None, None]:
    """
    获取 MySQL 连接的上下文管理器；使用完毕自动 commit/rollback，
    若启用连接池则归还连接，否则关闭。未配置时 yield None。
    """
    with _connection_impl(**kwargs) as conn:
        yield conn


@contextmanager
def get_session(**kwargs: Any) -> Generator["Connection | None", None, None]:
    """
    与 get_connection 同义，提供“会话”语义的 MySQL 连接。
    """
    with get_connection(**kwargs) as conn:
        yield conn
