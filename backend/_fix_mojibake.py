# -*- coding: utf-8 -*-
"""修复 MySQL 中双重编码的中文数据（latin1 -> utf8mb4 mojibake）。

原理：乱码值可以用 latin1 无损编码回原始 UTF-8 字节，再按 utf8 解码即还原中文。
已是正常中文的值 encode('latin1') 会抛异常（超出 latin1 范围），自动跳过。
"""
import sys

import pymysql

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = pymysql.connect(
    host="127.0.0.1", port=3306, user="root",
    password="k2q3#k5f", database="fpai",
    charset="utf8mb4", autocommit=False,
)

def _mysql_latin1_decode(s: str):
    """按 MySQL latin1(≈cp1252) 把乱码字符串还原为原始字节，再按 UTF-8 解码。

    MySQL 的 latin1 对 cp1252 未定义的 0x81/0x8D/0x8F/0x90/0x9D
    映射为 C1 控制符 U+0081 等，需要特殊处理。
    无法还原（说明不是乱码）时返回 None。
    """
    buf = bytearray()
    for ch in s:
        o = ord(ch)
        if o <= 0xFF:
            buf.append(o)  # latin1 区间（含 C1 控制符）直接取字节
        else:
            try:
                b = ch.encode("cp1252")
            except UnicodeEncodeError:
                return None  # 含中日韩等字符，是正常数据
            if len(b) != 1:
                return None
            buf.extend(b)
    return bytes(buf).decode("utf-8")


fixed_total = 0
try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = 'fpai'
              AND DATA_TYPE IN ('char','varchar','text','tinytext','mediumtext','longtext')
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """)
        text_cols = cur.fetchall()

        # 每个表的主键，用于定位行
        cur.execute("""
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = 'fpai' AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """)
        pk_map = {}
        for t, c in cur.fetchall():
            pk_map.setdefault(t, []).append(c)

        for table, col in text_cols:
            pks = pk_map.get(table)
            if not pks:
                continue
            cur.execute(f"SELECT {', '.join(f'`{p}`' for p in pks)}, `{col}` FROM `{table}`")
            rows = cur.fetchall()
            for row in rows:
                val = row[-1]
                if not val or not isinstance(val, str):
                    continue
                try:
                    repaired = _mysql_latin1_decode(val)
                except (UnicodeEncodeError, UnicodeDecodeError, ValueError):
                    continue  # 正常中文或非乱码内容，跳过
                if repaired is None:
                    continue
                if repaired == val:
                    continue  # 纯 ASCII，无变化
                # 保守起见：修复结果里应不含替换符
                if "�" in repaired:
                    continue
                where = " AND ".join(f"`{p}` = %s" for p in pks)
                cur.execute(
                    f"UPDATE `{table}` SET `{col}` = %s WHERE {where}",
                    (repaired, *row[:-1]),
                )
                fixed_total += 1
                print(f"[修复] {table}.{col} pk={row[:-1]}: {val[:30]!r} -> {repaired[:30]!r}")

    conn.commit()
    print(f"\n共修复 {fixed_total} 处")

    # 验证
    with conn.cursor() as cur:
        cur.execute("SELECT name, description FROM roles")
        print("roles:", cur.fetchall())
        cur.execute("SELECT name FROM users")
        print("users:", cur.fetchall())
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
