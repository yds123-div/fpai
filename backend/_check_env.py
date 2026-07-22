# -*- coding: utf-8 -*-
"""一次性连通性检查脚本：检查 .env 中各服务是否可达。"""
import os
import socket
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")


def tcp_check(name, host, port, timeout=5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            report(f"{name} TCP {host}:{port}", True, "端口可达")
            return True
    except Exception as e:
        report(f"{name} TCP {host}:{port}", False, f"{type(e).__name__}: {e}")
        return False


# ---------- 1. MySQL ----------
if tcp_check("MySQL", "127.0.0.1", 3306):
    try:
        import pymysql
        conn = pymysql.connect(
            host="127.0.0.1", port=3306, user="root",
            password="REDACTED", database="fpai", connect_timeout=5,
        )
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT COUNT(*) FROM users")
            user_cnt = cur.fetchone()[0]
        conn.close()
        report("MySQL 登录+库检查", True, f"fpai 库 {len(tables)} 张表, users 表 {user_cnt} 条记录")
        if not tables:
            report("MySQL 初始化脚本", False, "fpai 库为空, 需导入 cloudrun/mysql/init.sql")
    except Exception as e:
        report("MySQL 登录+库检查", False, f"{type(e).__name__}: {e}")

# ---------- 2. Redis ----------
if tcp_check("Redis", "localhost", 6379):
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, db=0, password="REDACTED", socket_timeout=5)
        info = r.ping()
        report("Redis PING", True, f"ping={info}")
    except Exception as e:
        report("Redis PING", False, f"{type(e).__name__}: {e}")

# ---------- 3. Milvus ----------
if tcp_check("Milvus", "localhost", 19530):
    try:
        from pymilvus import connections, utility
        connections.connect(alias="check", host="localhost", port="19530", timeout=8)
        cols = utility.list_collections(using="check")
        report("Milvus 连接", True, f"collections={cols}")
        connections.disconnect("check")
    except Exception as e:
        report("Milvus 连接", False, f"{type(e).__name__}: {e}")

# ---------- 4. MinIO ----------
if tcp_check("MinIO", "106.55.151.240", 9000, timeout=8):
    try:
        from minio import Minio
        client = Minio(
            "106.55.151.240:9000",
            access_key="REDACTED",
            secret_key="REDACTED",
            secure=False,
        )
        buckets = [b.name for b in client.list_buckets()]
        report("MinIO 登录", True, f"buckets={buckets}")
        for need in ("fpai-docs", "fpai-audit"):
            if need not in buckets:
                report(f"MinIO bucket {need}", False, "bucket 不存在")
    except Exception as e:
        report("MinIO 登录", False, f"{type(e).__name__}: {e}")

# ---------- 5. LLM (火山引擎 ark) ----------
try:
    import httpx
    resp = httpx.post(
        "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        headers={"Authorization": "Bearer REDACTED"},
        json={
            "model": "deepseek-v4-flash-260425",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 8,
        },
        timeout=30,
    )
    if resp.status_code == 200:
        content = resp.json()["choices"][0]["message"]["content"]
        report("LLM chat/completions", True, f"模型有回复, 长度={len(str(content))}")
    else:
        report("LLM chat/completions", False, f"HTTP {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    report("LLM chat/completions", False, f"{type(e).__name__}: {e}")

# ---------- 6. Embedding (火山引擎 ark) ----------
try:
    resp = httpx.post(
        "https://ark.cn-beijing.volces.com/api/plan/v3/embeddings",
        headers={"Authorization": "Bearer REDACTED"},
        json={"model": "doubao-embedding-vision", "input": ["测试"]},
        timeout=30,
    )
    if resp.status_code == 200:
        dim = len(resp.json()["data"][0]["embedding"])
        report("Embedding", True, f"向量维度={dim}")
    else:
        report("Embedding", False, f"HTTP {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    report("Embedding", False, f"{type(e).__name__}: {e}")

# ---------- 7. Reranker (SiliconFlow) ----------
try:
    resp = httpx.post(
        "https://api.siliconflow.cn/v1/rerank",
        headers={"Authorization": "Bearer REDACTED"},
        json={
            "model": "BAAI/bge-reranker-v2-m3",
            "query": "基金",
            "documents": ["货币基金风险低", "今天天气不错"],
        },
        timeout=30,
    )
    if resp.status_code == 200:
        report("Reranker", True, "重排序调用成功")
    else:
        report("Reranker", False, f"HTTP {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    report("Reranker", False, f"{type(e).__name__}: {e}")

# ---------- 8. 外部知识库 ----------
try:
    resp = httpx.get(
        "http://139.9.59.175:8080/api/v1/knowledge-bases",
        headers={"X-API-Key": "REDACTED"},
        timeout=10,
    )
    report("外部知识库", resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:150]}")
except Exception as e:
    report("外部知识库", False, f"{type(e).__name__}: {e}")

# ---------- 汇总 ----------
print("\n===== 汇总 =====")
failed = [n for n, ok, _ in results if not ok]
if failed:
    print("失败项:")
    for n in failed:
        print(" -", n)
    sys.exit(1)
print("全部通过")
