"""pkg.mysql_client 单元测试：配置判断与会话上下文."""
import os

import pytest

from pkg.mysql_client import get_connection, get_session, is_configured


def test_is_configured_without_env():
    """未设置 MYSQL_USER 时不应认为已配置."""
    try:
        orig = os.environ.pop("MYSQL_USER", None)
        assert is_configured() is False
    finally:
        if orig is not None:
            os.environ["MYSQL_USER"] = orig


def test_get_connection_without_config_yields_none():
    """未配置 MySQL 时 get_connection 应 yield None."""
    try:
        orig = os.environ.pop("MYSQL_USER", None)
        with get_connection() as conn:
            assert conn is None
    finally:
        if orig is not None:
            os.environ["MYSQL_USER"] = orig


def test_get_session_without_config_yields_none():
    """未配置时 get_session 应 yield None."""
    try:
        orig = os.environ.pop("MYSQL_USER", None)
        with get_session() as conn:
            assert conn is None
    finally:
        if orig is not None:
            os.environ["MYSQL_USER"] = orig
