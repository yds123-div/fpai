"""
T010a：从 MySQL 加载领域模型与数据源配置，构建 HTTP Fetcher 并注册，供 get_data 使用。
见 docs/领域模型与API适配器设计.md。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from data_access.domain_model import (
    DomainModelInfo,
    FieldDef,
    ModelMetadata,
    get_by_path,
)
from data_access.model_registry import register_model, register_fetcher


@dataclass
class DataSourceConfig:
    """数据源配置（与 MySQL data_sources 表 JSON 列对应）。"""
    type: str = "http_rest"
    base_url: str = ""
    auth_type: str = ""
    auth_config: dict[str, Any] = field(default_factory=dict)
    request_spec: dict[str, Any] = field(default_factory=dict)
    response_spec: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30


def _parse_json(val: Any) -> dict | list:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return {}
    return {}


def _build_url(base: str, path: str, path_params: dict[str, Any], query_params: dict[str, Any]) -> str:
    p = path
    for k, v in path_params.items():
        p = p.replace("{" + k + "}", str(v) if v is not None else "")
    url = (base.rstrip("/") + "/" + p.lstrip("/")) if base else p
    if query_params:
        from urllib.parse import urlencode
        url = url + ("&" if "?" in url else "?") + urlencode({k: v for k, v in query_params.items() if v is not None})
    return url


def _build_headers(auth_type: str, auth_config: dict[str, Any], extra: dict[str, str]) -> dict[str, str]:
    h = dict(extra)
    if auth_type == "bearer" and auth_config.get("token"):
        h["Authorization"] = "Bearer " + str(auth_config["token"])
    elif auth_type == "api_key":
        key = auth_config.get("header_name") or "X-API-Key"
        val = auth_config.get("api_key") or os.getenv("DATA_ACCESS_HTTP_API_KEY", "")
        if val:
            h[key] = str(val)
    return h


def build_http_fetcher(config: DataSourceConfig):
    """根据数据源配置构造 HTTP Fetcher，返回 (raw_list, total)。"""
    req = config.request_spec or {}
    resp_spec = config.response_spec or {}
    base_url = config.base_url or os.getenv("DATA_ACCESS_HTTP_BASE_URL", "")
    timeout = float(config.timeout_seconds or 30)
    method = (req.get("method") or "GET").upper()
    path = req.get("path") or ""
    query_params_spec = req.get("query_params") or []
    body_params_spec = req.get("body_params") or []
    path_params_spec = req.get("path_params") or []
    list_path = resp_spec.get("list_path") or ""
    total_path = resp_spec.get("total_path") or ""
    single_path = resp_spec.get("single_path") or ""

    def fetcher(model_code: str, request_params: dict[str, Any], org_id: str | None) -> tuple[list[dict[str, Any]], int | None]:
        path_params = {p.get("name", ""): request_params.get(p.get("name", "")) for p in path_params_spec}
        query_dict = {p.get("name", ""): request_params.get(p.get("name", "")) for p in query_params_spec}
        body_dict = {p.get("name", ""): request_params.get(p.get("name", "")) for p in body_params_spec} if body_params_spec else None
        url = _build_url(base_url, path, path_params, query_dict)
        headers = _build_headers(config.auth_type, config.auth_config or {}, req.get("headers") or {})
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                r = client.get(url, headers=headers)
            elif method == "POST":
                r = client.post(url, json=body_dict or {}, headers={**headers, "Content-Type": "application/json"})
            else:
                r = client.request(method, url, json=body_dict, headers=headers)
            r.raise_for_status()
            data = r.json()
        raw_list = get_by_path(data, list_path) if list_path else get_by_path(data, single_path)
        if raw_list is None:
            raw_list = []
        if not isinstance(raw_list, list):
            raw_list = [raw_list]
        total = get_by_path(data, total_path) if total_path else None
        if total is not None:
            total = int(total)
        return raw_list, total

    return fetcher


def load_from_mysql(org_id: str | None = None) -> list[tuple[DomainModelInfo, ModelMetadata, DataSourceConfig]]:
    """
    从 MySQL domain_models、domain_model_fields、data_sources 表加载配置。
    org_id 为 None 时只加载 org_id IS NULL 的数据源；否则加载该 org_id 或 NULL 的默认数据源。
    返回 [(DomainModelInfo, ModelMetadata, DataSourceConfig), ...]。
    """
    try:
        from pkg.mysql_client import get_connection, is_configured
    except ImportError:
        return []
    if not is_configured():
        return []
    result = []
    with get_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            cur.execute("SELECT model_code, name, description FROM domain_models")
            rows = cur.fetchall()
        except Exception:
            return []
        for row in rows:
            model_code = row[0]
            name = row[1] or model_code
            description = row[2] or ""
            info = DomainModelInfo(model_code=model_code, name=name, description=description)
            cur.execute(
                "SELECT field_name, data_type, is_required, description, default_value, source_path FROM domain_model_fields WHERE model_code = %s ORDER BY sort_order, id",
                (model_code,),
            )
            field_rows = cur.fetchall()
            fields = [
                FieldDef(
                    name=r[0],
                    data_type=r[1] or "string",
                    required=bool(r[2]),
                    description=r[3] or "",
                    default_value=r[4],
                    source_path=r[5] or "",
                )
                for r in field_rows
            ]
            metadata = ModelMetadata(model_code=model_code, fields=fields)
            if org_id is None:
                cur.execute(
                    "SELECT type, base_url, auth_type, auth_config, request_spec, response_spec, timeout_seconds FROM data_sources WHERE model_code = %s AND org_id IS NULL LIMIT 1",
                    (model_code,),
                )
            else:
                cur.execute(
                    "SELECT type, base_url, auth_type, auth_config, request_spec, response_spec, timeout_seconds FROM data_sources WHERE model_code = %s AND (org_id = %s OR org_id IS NULL) ORDER BY (org_id IS NULL) ASC LIMIT 1",
                    (model_code, org_id),
                )
            ds_row = cur.fetchone()
            if not ds_row:
                continue
            auth_cfg = _parse_json(ds_row[3])
            req_spec = _parse_json(ds_row[4])
            resp_spec = _parse_json(ds_row[5])
            config = DataSourceConfig(
                type=ds_row[0] or "http_rest",
                base_url=ds_row[1] or "",
                auth_type=ds_row[2] or "",
                auth_config=auth_cfg if isinstance(auth_cfg, dict) else {},
                request_spec=req_spec if isinstance(req_spec, dict) else {},
                response_spec=resp_spec if isinstance(resp_spec, dict) else {},
                timeout_seconds=int(ds_row[6]) if ds_row[6] is not None else 30,
            )
            result.append((info, metadata, config))
    return result


def load_from_mysql_and_register(org_id: str | None = None) -> int:
    """从 MySQL 加载领域模型与数据源并注册到 model_registry；返回注册数量。"""
    count = 0
    for info, metadata, config in load_from_mysql(org_id):
        if config.type != "http_rest":
            continue
        fetcher = build_http_fetcher(config)
        register_model(info, metadata)
        register_fetcher(info.model_code, fetcher)
        count += 1
    return count
