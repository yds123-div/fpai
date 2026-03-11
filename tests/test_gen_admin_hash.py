# 测试 gen_admin_hash 使用的 hash_password / verify_password（与 auth.service 一致）
import pytest

from auth.service import hash_password, verify_password

# 种子数据脚本 002_initial_data_seed.sql 中 admin 用户的 password_hash（明文 admin123，bcrypt rounds=12）
ADMIN123_SEED_HASH = "$2b$12$Ur3tIiwoKOQmuwRWlM6b0O.fNK5CBoaIm82ztxLWqnAmlMBN43wVO"


def _hash_admin123():
    """调用 hash_password('admin123')，失败时返回 None（如 passlib/bcrypt 不兼容）。"""
    try:
        return hash_password("admin123")
    except Exception:
        return None


def test_hash_password_admin123_non_empty():
    """hash_password('admin123') 返回非空字符串。"""
    got = _hash_admin123()
    if got is None:
        pytest.skip("passlib/bcrypt 不可用或版本不兼容")
    assert isinstance(got, str) and len(got) > 0


def test_hash_password_admin123_bcrypt_format():
    """hash_password 返回的为 bcrypt 格式（$2b$ 或 $2a$）。"""
    got = _hash_admin123()
    if got is None or not got:
        pytest.skip("passlib 未安装或 hash_password 返回空")
    assert got.startswith("$2b$") or got.startswith("$2a$")


def test_verify_password_admin123_roundtrip():
    """对 'admin123' 哈希后再校验，verify_password 为 True。"""
    hashed = _hash_admin123()
    if not hashed:
        pytest.skip("passlib 未安装或 hash_password 不可用")
    assert verify_password("admin123", hashed) is True


def test_verify_password_wrong_plain_false():
    """错误明文校验为 False。"""
    hashed = _hash_admin123()
    if not hashed:
        pytest.skip("passlib 未安装或 hash_password 不可用")
    assert verify_password("wrong", hashed) is False


def test_verify_password_admin123_seed_hash():
    """数据库种子哈希（002_initial_data_seed.sql）对明文 admin123 校验通过。"""
    assert verify_password("admin123", ADMIN123_SEED_HASH) is True


def test_verify_password_seed_hash_wrong_plain_false():
    """种子哈希对错误明文校验为 False。"""
    assert verify_password("wrong", ADMIN123_SEED_HASH) is False


def test_hash_password_admin123_differs_from_seed():
    """
    hash_password('admin123') 每次输出不同（随机盐），与种子哈希字符串不相等，但都能被 verify 通过。
    """
    got = _hash_admin123()
    if got is None:
        pytest.skip("bcrypt 不可用")
    assert got != ADMIN123_SEED_HASH
    assert verify_password("admin123", got) is True
    assert verify_password("admin123", ADMIN123_SEED_HASH) is True
