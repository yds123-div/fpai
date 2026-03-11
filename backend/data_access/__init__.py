# 业务数据访问层：可配置领域模型与统一取数（见 docs/领域模型与API适配器设计.md）
from data_access.domain_model import DomainModelInfo, FieldDef, ModelMetadata, apply_mapping, get_by_path
from data_access.model_registry import (
    register_model,
    register_fetcher,
    get_metadata as get_model_metadata_registry,
    list_models as list_models_registry,
    get_fetcher,
    clear_all as clear_model_registry,
)
from data_access.unified import get_data, list_models, get_model_metadata
from data_access.adapters.config_loader import (
    load_from_mysql,
    load_from_mysql_and_register,
    build_http_fetcher,
    DataSourceConfig,
)

__all__ = [
    "DomainModelInfo",
    "FieldDef",
    "ModelMetadata",
    "apply_mapping",
    "get_by_path",
    "register_model",
    "register_fetcher",
    "get_data",
    "list_models",
    "get_model_metadata",
    "get_model_metadata_registry",
    "list_models_registry",
    "get_fetcher",
    "clear_model_registry",
    "load_from_mysql",
    "load_from_mysql_and_register",
    "build_http_fetcher",
    "DataSourceConfig",
]
