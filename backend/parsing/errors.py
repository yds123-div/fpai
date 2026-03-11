# -*- coding: utf-8 -*-
from __future__ import annotations


class ParsingError(RuntimeError):
    """文档解析失败。"""


class MinerUNotAvailable(ParsingError):
    """MinerU 未安装或不可用。"""

