# -*- coding: utf-8 -*-
"""parsing：文档解析与版面识别封装（MinerU，可选依赖）。"""

from parsing.errors import MinerUNotAvailable, ParsingError
from parsing.service import parse_document_bytes, parse_document_file
from parsing.types import ParsedBlock, ParsedDocument

__all__ = [
    "ParsedBlock",
    "ParsedDocument",
    "ParsingError",
    "MinerUNotAvailable",
    "parse_document_bytes",
    "parse_document_file",
]

