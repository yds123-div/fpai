# -*- coding: utf-8 -*-
"""
MinerU 适配器（T031a）。

基于 WeKnora docreader/parser/mineru_parser.py 的已验证实现：
通过 MinerU HTTP API（/file_parse）进行版面分析、表格与公式识别、文本抽取。
未配置 MINERU_ENDPOINT 或服务不可用时抛出 MinerUNotAvailable。
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from parsing.errors import MinerUNotAvailable, ParsingError
from parsing.types import ParsedBlock, ParsedDocument

# MinerU API 路径（与 WeKnora 一致）
MINERU_PATH_DOCS = "/docs"
MINERU_PATH_FILE_PARSE = "/file_parse"

# 默认请求超时（秒）
DEFAULT_PARSE_TIMEOUT = 1000
DEFAULT_PING_TIMEOUT = 5


def _get_endpoint(options: dict[str, Any] | None) -> str:
    """从 options 或环境变量获取 MinerU 端点，末尾无斜杠。"""
    opts = options or {}
    endpoint = (opts.get("mineru_endpoint") or os.getenv("MINERU_ENDPOINT") or "").strip()
    return endpoint.rstrip("/")


def _mineru_ping(endpoint: str, timeout: int = DEFAULT_PING_TIMEOUT) -> bool:
    """检查 MinerU API 是否可用（GET /docs）。"""
    if not endpoint:
        return False
    try:
        import httpx
        with httpx.Client(timeout=timeout) as client:
            r = client.get(endpoint + MINERU_PATH_DOCS)
            r.raise_for_status()
            return True
    except Exception:
        return False


def _markdownify_if_available(html_or_md: str) -> str:
    """若已安装 markdownify，将 HTML 转为 Markdown；否则原样返回。"""
    if not (html_or_md or html_or_md.strip()):
        return html_or_md or ""
    try:
        import markdownify
        return markdownify.markdownify(html_or_md)
    except ImportError:
        return html_or_md


def parse_with_mineru(
    content: bytes,
    *,
    filename: str = "",
    mime_type: str = "",
    doc_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> ParsedDocument:
    """
    使用 MinerU HTTP API 对 PDF/图片做版面分析与文本抽取，并映射为 ParsedDocument。

    与 WeKnora StdMinerUParser.parse_into_text 对齐：
    - POST {MINERU_ENDPOINT}/file_parse，表单 return_md=True、return_images=True、
      table_enable、formula_enable、lang_list 等；
    - 响应 results.files.md_content 作为主文本，可选 markdownify 转表格；
    - 不依赖 docreader，仅复用其 API 契约与参数。
    """
    options = options or {}
    endpoint = _get_endpoint(options)
    if not endpoint:
        raise MinerUNotAvailable("未配置 MINERU_ENDPOINT，无法调用 MinerU 解析服务")

    if not _mineru_ping(endpoint, timeout=options.get("ping_timeout", DEFAULT_PING_TIMEOUT)):
        raise MinerUNotAvailable(f"MinerU 服务不可用: {endpoint}")

    timeout = options.get("timeout") or DEFAULT_PARSE_TIMEOUT
    return_images = options.get("return_images", True)
    enable_markdownify = options.get("enable_markdownify", True)

    try:
        import httpx
    except ImportError as e:
        raise MinerUNotAvailable(f"需要 httpx 才能调用 MinerU API: {e}") from e

    form_data = {
        "return_md": True,
        "return_images": return_images,
        "lang_list": ["ch", "en"],
        "table_enable": True,
        "formula_enable": True,
        "parse_method": "auto",
        "start_page_id": 0,
        "end_page_id": 99999,
        "backend": "pipeline",
        "response_format_zip": False,
        "return_middle_json": False,
        "return_model_output": False,
        "return_content_list": False,
    }
    files = {"files": content}

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint + MINERU_PATH_FILE_PARSE,
                data=form_data,
                files=files,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise ParsingError(f"MinerU API 返回错误: {e.response.status_code}") from e
    except Exception as e:
        raise ParsingError(f"MinerU 解析失败: {e}") from e

    try:
        results = data.get("results") or {}
        files_result = results.get("files") or {}
        md_content = files_result.get("md_content") or ""
    except (AttributeError, TypeError) as e:
        raise ParsingError(f"MinerU 响应格式异常: {e}") from e

    if enable_markdownify and md_content:
        md_content = _markdownify_if_available(md_content)

    images = files_result.get("images") or {}
    meta: dict[str, Any] = {"engine": "mineru", "image_count": len(images)}
    if filename:
        meta["filename"] = filename
    if mime_type:
        meta["mime_type"] = mime_type

    blocks: list[ParsedBlock] = []
    if md_content.strip():
        blocks.append(ParsedBlock(type="text", text=md_content.strip(), meta={"source": "md_content"}))

    return ParsedDocument(
        doc_id=doc_id or uuid.uuid4().hex,
        filename=filename or "",
        mime_type=mime_type or "",
        blocks=blocks,
        meta=meta,
    )
