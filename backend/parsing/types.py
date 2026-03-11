# -*- coding: utf-8 -*-
"""
文档解析输出类型（T031a）。

目标：对接 MinerU 的版面分析结果，输出结构化文本供 ingestion 分块与向量化使用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


BlockType = Literal["text", "title", "table", "formula", "image", "unknown"]


@dataclass
class ParsedBlock:
    """解析后的结构化块（按阅读顺序）。"""

    type: BlockType = "text"
    text: str = ""
    page: int | None = None
    bbox: list[float] | None = None  # [x1,y1,x2,y2]，可选
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析结果：blocks + 便捷的 full_text。"""

    doc_id: str = ""
    filename: str = ""
    mime_type: str = ""
    blocks: list[ParsedBlock] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        parts = []
        for b in self.blocks:
            t = (b.text or "").strip()
            if t:
                parts.append(t)
        return "\n\n".join(parts).strip()

