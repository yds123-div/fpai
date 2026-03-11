"""data_access 单元测试：统一取数 get_data、list_models、get_model_metadata、映射与权限过滤、熔断。"""
import pytest

from data_access._circuit import reset as circuit_reset, record_failure


def setup_function():
    circuit_reset(None)
    try:
        from data_access import clear_model_registry
        clear_model_registry()
    except Exception:
        pass


def test_get_data_no_model_returns_empty():
    """未注册模型或 Fetcher 时 get_data 返回 ([], 0)。"""
    from data_access import get_data, clear_model_registry
    clear_model_registry()
    records, total = get_data("unknown_model", {})
    assert records == [] and total == 0


def test_get_data_with_registered_model_and_fetcher():
    """注册模型元数据与 Fetcher 后，get_data 返回映射后的 records 与 total。"""
    from data_access import (
        get_data,
        register_model,
        register_fetcher,
        DomainModelInfo,
        ModelMetadata,
        FieldDef,
        clear_model_registry,
    )
    clear_model_registry()
    circuit_reset(None)
    register_model(
        DomainModelInfo("M001", "测试模型", ""),
        ModelMetadata("M001", [
            FieldDef("id", "string", True, "", None, "$.id"),
            FieldDef("name", "string", False, "", None, "$.name"),
        ]),
    )
    def _fetcher(mc, params, org_id):
        return [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}], 2
    register_fetcher("M001", _fetcher)
    records, total = get_data("M001", {}, use_cache=False)
    assert len(records) == 2 and records[0]["id"] == "1" and records[0]["name"] == "A"
    assert total == 2


def test_get_data_permission_filter():
    """get_data 按 permission_context.product_pool_ids 过滤记录。"""
    from data_access import (
        get_data,
        register_model,
        register_fetcher,
        DomainModelInfo,
        ModelMetadata,
        FieldDef,
        clear_model_registry,
    )
    clear_model_registry()
    circuit_reset(None)
    register_model(
        DomainModelInfo("M002", "带池", ""),
        ModelMetadata("M002", [
            FieldDef("id", "string", True, "", None, "$.id"),
            FieldDef("product_pool_id", "string", False, "", None, "$.pool"),
        ]),
    )
    def _fetcher(mc, params, org_id):
        return [{"id": "1", "pool": "p1"}, {"id": "2", "pool": "p2"}, {"id": "3", "pool": "p1"}], 3
    register_fetcher("M002", _fetcher)
    records, total = get_data("M002", {}, permission_context={"product_pool_ids": ["p1"]}, use_cache=False)
    assert len(records) == 2 and all(r["product_pool_id"] == "p1" for r in records)


def test_list_models_and_get_model_metadata():
    """list_models 返回已注册模型列表；get_model_metadata 返回元数据。"""
    from data_access import (
        list_models,
        get_model_metadata,
        register_model,
        DomainModelInfo,
        ModelMetadata,
        FieldDef,
        clear_model_registry,
    )
    clear_model_registry()
    assert list_models() == []
    register_model(
        DomainModelInfo("0731H016", "基金基本信息", "示例"),
        ModelMetadata("0731H016", [FieldDef("fund_code", "string", True, "", None, "$.fundCode")]),
    )
    assert len(list_models()) == 1 and list_models()[0].model_code == "0731H016"
    meta = get_model_metadata("0731H016")
    assert meta is not None and meta.model_code == "0731H016" and len(meta.fields) == 1
    assert meta.fields[0].name == "fund_code" and meta.fields[0].source_path == "$.fundCode"


def test_apply_mapping_source_path():
    """apply_mapping 按 source_path 从原始项取值。"""
    from data_access.domain_model import apply_mapping, ModelMetadata, FieldDef
    meta = ModelMetadata("X", [
        FieldDef("a", "string", False, "", None, "$.x"),
        FieldDef("b", "string", False, "", "default_b", "$.y"),
    ])
    record = apply_mapping({"x": "v1", "y": "v2"}, meta)
    assert record["a"] == "v1" and record["b"] == "v2"
    record2 = apply_mapping({"x": "only"}, meta)
    assert record2["a"] == "only" and record2["b"] == "default_b"


def test_get_data_circuit_open_returns_empty():
    """熔断打开时 get_data 返回 ([], 0)。"""
    from data_access import get_data, register_model, register_fetcher, DomainModelInfo, ModelMetadata, FieldDef, clear_model_registry
    clear_model_registry()
    circuit_reset(None)
    register_model(DomainModelInfo("M3", "M", ""), ModelMetadata("M3", [FieldDef("id", "string", True, "", None, "$.id")]))
    register_fetcher("M3", lambda mc, p, o: ([{"id": "1"}], 1))
    record_failure("default", threshold=1, window_seconds=10.0)
    records, total = get_data("M3", {}, org_id="default", use_cache=False)
    assert records == [] and total == 0


# ---------- T010a：基于配置的 API 适配器运行时 ----------


def test_build_http_fetcher_parses_response_by_list_path(monkeypatch):
    """build_http_fetcher 按 response_spec.list_path、total_path 解析响应。"""
    from data_access.adapters.config_loader import build_http_fetcher, DataSourceConfig
    resp_body = {"data": {"list": [{"id": "1", "name": "A"}], "total": 1}}
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return resp_body
    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json=None, headers=None): return FakeResponse()
    monkeypatch.setattr("data_access.adapters.config_loader.httpx.Client", lambda timeout: FakeClient())
    config = DataSourceConfig(
        base_url="http://fake",
        request_spec={"method": "POST", "path": "/api", "body_params": [{"name": "q"}]},
        response_spec={"list_path": "$.data.list", "total_path": "$.data.total"},
        timeout_seconds=5,
    )
    fetcher = build_http_fetcher(config)
    raw_list, total = fetcher("M", {"q": "x"}, None)
    assert len(raw_list) == 1 and raw_list[0]["id"] == "1"
    assert total == 1


def test_load_from_mysql_returns_empty_when_not_configured(monkeypatch):
    """MySQL 未配置时 load_from_mysql 返回 []。"""
    from data_access.adapters.config_loader import load_from_mysql
    monkeypatch.setattr("pkg.mysql_client.is_configured", lambda: False)
    assert load_from_mysql() == []


def test_load_from_mysql_and_register_returns_zero_when_no_mysql(monkeypatch):
    """MySQL 不可用时 load_from_mysql_and_register 返回 0。"""
    monkeypatch.setattr("pkg.mysql_client.is_configured", lambda: False)
    from data_access import load_from_mysql_and_register, clear_model_registry
    clear_model_registry()
    n = load_from_mysql_and_register()
    assert n == 0
