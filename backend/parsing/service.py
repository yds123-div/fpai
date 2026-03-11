# -*- coding: utf-8 -*-
"""
文档解析服务（T031a）。

对上提供稳定接口：parse_document_bytes / parse_document_file。
对内可选择 MinerU 或后续其它引擎；当前以 MinerU 为主，可选依赖。
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from parsing.errors import MinerUNotAvailable, ParsingError
from parsing.mineru_adapter import parse_with_mineru
from parsing.types import ParsedDocument


def _guess_mime(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename or "")
    return mt or ""


def parse_document_bytes(
    content: bytes,
    *,
    filename: str = "",
    mime_type: str | None = None,
    engine: str = "mineru",
    options: dict[str, Any] | None = None,
) -> ParsedDocument:
    """
    解析二进制文档内容为结构化文本。

    Args:
        content: 文件 bytes。
        filename: 原始文件名（用于推断 mime）。
        mime_type: 显式指定 mime；不传则按文件名推断。
        engine: 解析引擎，当前支持 mineru。
        options: 引擎选项。
    """
    if not content:
        raise ParsingError("content 不能为空")
    mt = (mime_type or "").strip() or _guess_mime(filename)
    eng = (engine or "mineru").strip().lower()
    if eng == "mineru":
        return parse_with_mineru(content, filename=filename, mime_type=mt, options=options)
    raise ParsingError(f"不支持的解析引擎: {engine}")


def parse_document_file(
    path: str | Path,
    *,
    engine: str = "mineru",
    options: dict[str, Any] | None = None,
) -> ParsedDocument:
    """解析本地文件路径。"""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise ParsingError(f"文件不存在: {p}")
    content = p.read_bytes()
    return parse_document_bytes(content, filename=p.name, mime_type=_guess_mime(p.name), engine=engine, options=options)


__all__ = [
    "ParsedDocument",
    "MinerUNotAvailable",
    "ParsingError",
    "parse_document_bytes",
    "parse_document_file",
]

