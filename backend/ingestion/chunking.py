# -*- coding: utf-8 -*-
"""
文档分块：将解析后的全文切分为适合向量化的 chunk，供 ingestion 写 Milvus。

T032：与 technical_design §4.3 chunk 一致；分块策略可配置（按长度、重叠、段落）。
"""
from __future__ import annotations

import re


def chunk_text(
    text: str,
    *,
    chunk_size: int = 500,
    overlap: int = 50,
    split_by_paragraph: bool = True,
) -> list[str]:
    """
    将文本切分为若干 chunk，尽量在段落边界切分，超长段落按 chunk_size 滑动窗口。

    Args:
        text: 全文。
        chunk_size: 单块最大字符数（约）。
        overlap: 滑动重叠字符数。
        split_by_paragraph: 是否优先按双换行分段再按长度切。

    Returns:
        非空字符串列表，顺序与原文一致。
    """
    text = (text or "").strip()
    if not text:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 10)
    step = max(1, chunk_size - overlap)

    if split_by_paragraph:
        # 先按 \n\n 或 \r\n\r\n 分段
        parts = re.split(r"\n\s*\n|\r\n\s*\r\n", text)
        chunks: list[str] = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if len(p) <= chunk_size:
                chunks.append(p)
                continue
            # 超长段落按步长滑动
            start = 0
            while start < len(p):
                end = min(start + chunk_size, len(p))
                chunks.append(p[start:end].strip())
                if end >= len(p):
                    break
                start = end - overlap
        return [c for c in chunks if c]
    else:
        # 纯滑动窗口
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = end - overlap
        return chunks
