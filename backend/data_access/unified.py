"""
统一取数接口 get_data、list_models、get_model_metadata；权限过滤、缓存、熔断。
见 docs/领域模型与API适配器设计.md §6。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pkg.redis_client import get_client as get_redis_client

from data_access.domain_model import ModelMetadata, apply_mapping
from data_access.model_registry import (
    get_fetcher,
    get_metadata as _get_metadata,
    list_models as _list_models,
)
from data_access._circuit import is_open, record_failure, record_success

# get_data 缓存 TTL（秒）
GET_DATA_CACHE_TTL = 300
GET_DATA_CACHE_PREFIX = "data_access:get_data:"


def _params_hash(request_params: dict[str, Any]) -> str:
    try:
        raw = json.dumps(request_params, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]
    except (TypeError, ValueError):
        return ""


def _get_data_cache(model_code: str, request_params: dict[str, Any]) -> tuple[list[dict], int] | None:
    client = get_redis_client()
    if not client:
        return None
    key = f"{GET_DATA_CACHE_PREFIX}{model_code}:{_params_hash(request_params)}"
    try:
        data = client.get(key)
        if data:
            decoded = json.loads(data.decode("utf-8"))
            return (decoded.get("records") or [], decoded.get("total", 0))
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _set_data_cache(model_code: str, request_params: dict[str, Any], records: list[dict], total: int) -> None:
    client = get_redis_client()
    if not client:
        return
    key = f"{GET_DATA_CACHE_PREFIX}{model_code}:{_params_hash(request_params)}"
    try:
        client.setex(key, GET_DATA_CACHE_TTL, json.dumps({"records": records, "total": total}, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        pass


def _permission_filter_records(records: list[dict[str, Any]], permission_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """仅保留 product_pool_id / source_org 在 product_pool_ids 内的记录。"""
    pool_ids = None
    if permission_context:
        pool_ids = permission_context.get("product_pool_ids") or permission_context.get("productPoolIds")
    if not pool_ids:
        return records
    out = []
    for r in records:
        pid = r.get("product_pool_id") or r.get("source_org")
        if pid is None or pid in pool_ids:
            out.append(r)
    return out


def get_data(
    model_code: str,
    request_params: dict[str, Any] | None = None,
    permission_context: dict[str, Any] | None = None,
    org_id: str | None = None,
    use_cache: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """
    按领域模型编码取数；返回 (records, total)。
    若无该模型或 Fetcher 则返回 ([], 0)。含权限过滤、可选缓存、熔断。
    """
    params = request_params or {}
    oid = org_id or (permission_context or {}).get("org_id", "default")

    if is_open(oid):
        return [], 0

    if use_cache:
        cached = _get_data_cache(model_code, params)
        if cached is not None:
            records, total = cached
            filtered = _permission_filter_records(records, permission_context)
            return filtered, total

    metadata = _get_metadata(model_code)
    fetcher = get_fetcher(model_code)
    if not metadata or not fetcher:
        return [], 0

    try:
        raw_list, total = fetcher(model_code, params, org_id)
        if raw_list is None:
            raw_list = []
        if total is None:
            total = len(raw_list)
        records = [apply_mapping(item, metadata) for item in raw_list]
        filtered = _permission_filter_records(records, permission_context)
        if use_cache:
            _set_data_cache(model_code, params, filtered, len(filtered))
        record_success(oid)
        return filtered, total
    except Exception:
        record_failure(oid)
        raise


def list_models() -> list:
    """列出已配置的领域模型摘要（DomainModelInfo 列表）。"""
    return _list_models()


def get_model_metadata(model_code: str) -> ModelMetadata | None:
    """查询某模型的完整元数据。"""
    return _get_metadata(model_code)
