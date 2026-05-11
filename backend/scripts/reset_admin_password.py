#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重置 admin 用户密码脚本。
用法：cd backend && python scripts/reset_admin_password.py [新密码]
不传参数时默认重置为 admin123
"""
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path
_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from dotenv import load_dotenv
load_dotenv(_backend / ".env")

from pkg.mysql_client import is_configured, get_connection
from auth.service import reset_user_password, hash_password

def main():
    new_password = sys.argv[1] if len(sys.argv) > 1 else "admin123"

    if not is_configured():
        print("❌ MySQL 未配置，请检查 .env 中的 MYSQL_* 变量")
        sys.exit(1)

    # 查找 admin 用户
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, account, password_hash FROM users WHERE account = 'admin' LIMIT 1")
                row = cur.fetchone()
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        sys.exit(1)

    if not row:
        print("❌ 未找到 account='admin' 的用户，请先创建用户")
        sys.exit(1)

    user_id, account, old_hash = row
    print(f"✅ 找到用户: id={user_id}, account={account}")
    print(f"   旧 password_hash 前缀: {(old_hash or '')[:20]}...")

    # 重置密码：reset_user_password 内部会做 bcrypt(SHA256(明文))
    ok = reset_user_password(str(user_id), new_password)
    if not ok:
        print("❌ 重置失败，请检查日志")
        sys.exit(1)

    # 验证新 hash 已写入
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s LIMIT 1", (user_id,))
            new_hash = cur.fetchone()[0]

    print(f"✅ 密码重置成功！新 password_hash 前缀: {(new_hash or '')[:20]}...")
    print(f"   账号: admin")
    print(f"   密码: {new_password}")
    print()
    print("⚠️  前端登录时需传 SHA256(明文密码).hex，请确认前端已做 SHA256 处理。")
    print("   若前端直接传明文，登录仍会失败。")

if __name__ == "__main__":
    main()
