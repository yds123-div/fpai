"""
可配置领域模型与元数据，见 docs/领域模型与API适配器设计.md。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldDef:
    """元数据字段：名称、类型、必填、描述、默认值、source_path（映射用）。"""
    name: str
    data_type: str = "string"
    required: bool = False
    description: str = ""
    default_value: Any = None
    source_path: str = ""


@dataclass
class ModelMetadata:
    """领域模型元数据：模型编码与字段列表。"""
    model_code: str
    fields: list[FieldDef] = field(default_factory=list)

    def field_by_name(self, name: str) -> FieldDef | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None


@dataclass
class DomainModelInfo:
    """领域模型摘要：列出已配置模型时使用。"""
    model_code: str
    name: str
    description: str = ""


def get_by_path(obj: Any, path: str) -> Any:
    """简单路径取值：$.a.b 或 a.b，支持一层索引 [0]。供响应解析与映射使用。"""
    if not path or not isinstance(obj, (dict, list)):
        return None
    s = path.strip()
    if s.startswith("$."):
        s = s[2:]
    if not s:
        return obj
    parts = s.replace("[", ".").replace("]", "").split(".")
    cur: Any = obj
    for p in parts:
        if not p:
            continue
        if isinstance(cur, list) and p.isdigit():
            idx = int(p)
            if 0 <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def apply_mapping(raw_item: dict[str, Any], metadata: ModelMetadata) -> dict[str, Any]:
    """将原始响应单条按元数据 source_path 映射为领域模型记录。"""
    record: dict[str, Any] = {}
    for fd in metadata.fields:
        if fd.source_path:
            val = get_by_path(raw_item, fd.source_path)
        else:
            val = raw_item.get(fd.name)
        if val is None and fd.default_value is not None:
            val = fd.default_value
        record[fd.name] = val
    return record
