# -*- coding: utf-8 -*-
"""
外部知识库系统同步：

- 从外部知识库系统拉取“知识库名称 + UUID”列表
- upsert 到本地 MySQL knowledge_bases 表

外部接口约定（可通过环境变量配置）：
- EXTERNAL_KB_LIST_URL：完整列表接口地址，如 http://localhost:8080/api/v1/knowledge-bases
- EXTERNAL_KB_API_KEY：鉴权 key（请求头 X-API-Key）

返回约定尽量宽松：
- 若响应为 dict 且包含 items/list/data 任一字段，优先取该字段作为数组
- 若响应本身是 list，直接作为数组
每个元素支持字段：uuid/name（或 id/title 兼容）。
"""

from __future__ import annotations

import os
from typing import Any

from pkg.logger import get_logger

from knowledge.store import upsert_knowledge_bases

logger = get_logger(__name__)


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("items", "list", "data", "knowledge_bases"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def sync_knowledge_bases_once() -> dict[str, Any]:
    """
    同步一次，返回：
    { ok: bool, count: int, message: str }
    """
    url = (os.getenv("EXTERNAL_KB_LIST_URL") or "").strip()
    api_key = (os.getenv("EXTERNAL_KB_API_KEY") or "").strip()
    if not url:
        return {"ok": False, "count": 0, "message": "未配置 EXTERNAL_KB_LIST_URL"}

    try:
        import httpx
    except ImportError:
        return {"ok": False, "count": 0, "message": "后端缺少 httpx 依赖"}

    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        return {"ok": False, "count": 0, "message": f"拉取外部知识库列表失败：{e}"}

    items = _extract_items(payload)
    count = upsert_knowledge_bases(items)
    return {"ok": True, "count": count, "message": "ok"}

