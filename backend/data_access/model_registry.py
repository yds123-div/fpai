"""
领域模型与数据获取器注册表：按 model_code 解析模型元数据与 Fetcher，供 get_data 使用。
T010a 可从 MySQL/YAML 加载后在此注册。
"""
from __future__ import annotations

from typing import Any, Callable

from data_access.domain_model import DomainModelInfo, ModelMetadata

# Fetcher: (model_code, request_params, org_id) -> (raw_records: list[dict], total: int | None)
DataFetcher = Callable[[str, dict[str, Any], str | None], tuple[list[dict[str, Any]], int | None]]

_models: dict[str, tuple[DomainModelInfo, ModelMetadata]] = {}
_fetchers: dict[str, DataFetcher] = {}


def register_model(info: DomainModelInfo, metadata: ModelMetadata) -> None:
    """注册领域模型及其元数据。"""
    _models[info.model_code] = (info, metadata)


def register_fetcher(model_code: str, fetcher: DataFetcher) -> None:
    """注册该 model_code 的数据获取器；返回 (raw_list, total)。"""
    _fetchers[model_code] = fetcher


def get_model_info(model_code: str) -> DomainModelInfo | None:
    """获取领域模型摘要。"""
    t = _models.get(model_code)
    return t[0] if t else None


def get_metadata(model_code: str) -> ModelMetadata | None:
    """获取领域模型元数据。"""
    t = _models.get(model_code)
    return t[1] if t else None


def get_fetcher(model_code: str) -> DataFetcher | None:
    """获取该 model_code 的 Fetcher。"""
    return _fetchers.get(model_code)


def list_models() -> list[DomainModelInfo]:
    """列出已注册的领域模型。"""
    return [info for info, _ in _models.values()]


def clear_models() -> None:
    """测试用：清空模型注册表。"""
    _models.clear()


def clear_fetchers() -> None:
    """测试用：清空 Fetcher 注册表。"""
    _fetchers.clear()


def clear_all() -> None:
    """测试用：清空模型与 Fetcher。"""
    _models.clear()
    _fetchers.clear()
