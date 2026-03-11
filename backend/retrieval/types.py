"""检索服务数据类型：chunk、citation、retrieve 与 generateAnswer 的入参/出参."""
from dataclasses import dataclass
from typing import Any


@dataclass
class Citation:
    """引用：与 technical_design 中 citations 一致，供前端与审计展示。"""
    doc_id: str
    source: str
    chunk_text: str
    score: float = 0.0


@dataclass
class RetrieveResult:
    """retrieve() 返回：chunks、scores、citations 一一对应。"""
    chunks: list[dict[str, Any]]
    scores: list[float]
    citations: list[Citation]


@dataclass
class GenerateAnswerResult:
    """generateAnswer() 返回。"""
    answer_blocks: list[str]
    citations: list[Citation]
