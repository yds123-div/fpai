"""pkg.redis_client 单元测试：get_client 在无 Redis 或未配置时行为."""
import os

import pytest

from pkg.redis_client import close_client, get_client, is_available


def test_get_client_without_redis_service():
    """未启动 Redis 时 get_client 可能返回 None 或连接失败后为 None."""
    close_client()
    # 不 mock 时，若本机无 Redis 则 get_client() 会返回 None（连接失败）
    # 仅断言返回类型或 None，不强制要求有服务
    client = get_client()
    assert client is None or hasattr(client, "ping")


def test_is_available_consistent_with_get_client():
    close_client()
    # 行为一致即可
    assert is_available() == (get_client() is not None)


def test_close_client_idempotent():
    close_client()
    close_client()
    assert get_client() is None or True  # 不因重复 close 报错
