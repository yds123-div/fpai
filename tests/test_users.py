# -*- coding: utf-8 -*-
"""
用户管理 service 测试：create_user（通过 mock MySQL 隔离数据库）。

运行方式（需在 backend 目录下，以便导入 auth.service）：
  cd backend
  pytest ../tests/test_users.py -v
"""
from __future__ import annotations

import pytest

# 在 backend 下运行时 auth / pkg 可直接导入
try:
    from auth.service import create_user
except ImportError:
    pytest.skip("需在 backend 目录下运行 pytest", allow_module_level=True)


# ---------- create_user 单元测试（mock MySQL） ----------


def test_create_user_empty_account_returns_none():
    """账号为空时 create_user 返回 None。"""
    assert create_user("", "pwd123", "Name", "", "") is None
    assert create_user("  ", "pwd123") is None


def test_create_user_empty_password_returns_none():
    """密码为空时 create_user 返回 None（hash_password 返回空且 bcrypt 可用时）。"""
    from unittest.mock import patch
    with patch("auth.service.mysql_configured", return_value=True):
        with patch("auth.service.get_connection"):
            result = create_user("newaccount", "", "Name", "", "")
    assert result is None


def test_create_user_mysql_not_configured_returns_none():
    """MySQL 未配置时 create_user 返回 None。"""
    from unittest.mock import patch
    with patch("auth.service.mysql_configured", return_value=False):
        result = create_user("any_account", "any_pwd", "Name", "", "")
    assert result is None


def test_create_user_duplicate_account_returns_none():
    """账号已存在时 create_user 返回 None。"""
    from unittest.mock import patch, MagicMock
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [(1,)]  # SELECT id FROM users WHERE account = %s 返回已有记录
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    with patch("auth.service.mysql_configured", return_value=True):
        with patch("auth.service.get_connection", return_value=mock_conn):
            result = create_user("existing", "pwd123", "Name", "", "")
    assert result is None


def test_create_user_success_returns_user_dict():
    """create_user 成功时返回包含 id、account、name、employee_no、email 的字典。"""
    from unittest.mock import patch, MagicMock
    # 第一次 get_connection：检查重复 + INSERT
    conn1 = MagicMock()
    cur1 = MagicMock()
    cur1.fetchone.side_effect = [None]  # 不重复
    cur1.__enter__ = MagicMock(return_value=cur1)
    cur1.__exit__ = MagicMock(return_value=False)
    conn1.cursor.return_value = cur1
    conn1.__enter__ = MagicMock(return_value=conn1)
    conn1.__exit__ = MagicMock(return_value=False)
    # 第二次 get_connection：INSERT 后按 account 再查
    conn2 = MagicMock()
    cur2 = MagicMock()
    cur2.fetchone.return_value = (42, "newuser", "Display Name", "E001", "u@example.com")
    cur2.__enter__ = MagicMock(return_value=cur2)
    cur2.__exit__ = MagicMock(return_value=False)
    conn2.cursor.return_value = cur2
    conn2.__enter__ = MagicMock(return_value=conn2)
    conn2.__exit__ = MagicMock(return_value=False)
    with patch("auth.service.mysql_configured", return_value=True):
        with patch("auth.service.get_connection", side_effect=[conn1, conn2]):
            result = create_user("newuser", "Secret123", "Display Name", "E001", "u@example.com")
    assert result is not None
    assert result.get("id") == "42"
    assert result.get("account") == "newuser"
    assert result.get("name") == "Display Name"
    assert result.get("employee_no") == "E001"
    assert result.get("email") == "u@example.com"
    assert "password_hash" not in result


def test_create_user_strips_whitespace():
    """create_user 对 account、name、employee_no、email 做 strip。"""
    from unittest.mock import patch, MagicMock
    conn1 = MagicMock()
    cur1 = MagicMock()
    cur1.fetchone.return_value = None
    cur1.__enter__ = MagicMock(return_value=cur1)
    cur1.__exit__ = MagicMock(return_value=False)
    conn1.cursor.return_value = cur1
    conn1.__enter__ = MagicMock(return_value=conn1)
    conn1.__exit__ = MagicMock(return_value=False)
    conn2 = MagicMock()
    cur2 = MagicMock()
    cur2.fetchone.return_value = (99, "trimmed", "Trimmed Name", "E2", "e@x.com")
    cur2.__enter__ = MagicMock(return_value=cur2)
    cur2.__exit__ = MagicMock(return_value=False)
    conn2.cursor.return_value = cur2
    conn2.__enter__ = MagicMock(return_value=conn2)
    conn2.__exit__ = MagicMock(return_value=False)
    with patch("auth.service.mysql_configured", return_value=True):
        with patch("auth.service.get_connection", side_effect=[conn1, conn2]):
            result = create_user("  trimmed  ", "pwd", "  Trimmed Name  ", " E2 ", " e@x.com ")
    assert result is not None
    assert result["account"] == "trimmed"
    assert result["name"] == "Trimmed Name"
    assert result["employee_no"] == "E2"
    assert result["email"] == "e@x.com"
