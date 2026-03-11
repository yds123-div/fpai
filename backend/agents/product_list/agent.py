# -*- coding: utf-8 -*-
"""
产品列表查询智能体：调用 data_access 统一接口返回可售产品列表（筛选、分页）。

T018：向 AgentScope 注册为工具 product_list_query；供路由等 toolkit 使用。
"""
from __future__ import annotations

import json
from typing import Any

from data_access import get_data

try:
    from agentscope.tool import ToolResponse
    from agentscope.message import TextBlock
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    ToolResponse = None  # type: ignore[misc, assignment]
    TextBlock = None  # type: ignore[misc, assignment]
    _AGENTSCOPE_AVAILABLE = False

# 默认产品列表领域模型编码（与 data_access 注册一致，可配置）
DEFAULT_PRODUCT_MODEL_CODE = "products"


def query_product_list(
    page: int = 1,
    page_size: int = 10,
    product_type: str | None = None,
    keyword: str | None = None,
    permission_context: dict[str, Any] | None = None,
    model_code: str = DEFAULT_PRODUCT_MODEL_CODE,
) -> dict[str, Any]:
    """
    调用 data_access 统一接口返回可售产品列表（筛选、分页）。

    Returns:
        products: list[dict] 产品记录
        total: int 总数
        summary: str 简短摘要，便于展示
    """
    request_params: dict[str, Any] = {
        "page": max(1, page),
        "page_size": min(max(1, page_size), 100),
    }
    if product_type:
        request_params["product_type"] = product_type
    if keyword:
        request_params["keyword"] = keyword
    try:
        records, total = get_data(
            model_code=model_code,
            request_params=request_params,
            permission_context=permission_context,
        )
    except Exception:
        records = []
        total = 0
    if not records:
        summary = "当前无符合条件的产品。"
    else:
        summary = f"共 {total} 条可售产品，当前页 {len(records)} 条（第 {page} 页）。"
    return {
        "products": records,
        "total": total,
        "summary": summary,
    }


def _parse_filters(filters: str) -> dict[str, Any]:
    """将 filters 字符串解析为 request_params（支持 JSON 或简单关键词）。"""
    filters = (filters or "").strip()
    if not filters:
        return {}
    try:
        data = json.loads(filters)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None and v != ""}
    except (json.JSONDecodeError, TypeError):
        pass
    return {"keyword": filters}


async def product_list_query(filters: str = "") -> Any:
    """
    产品列表查询，包装为 ToolResponse。供 toolkit.register_tool_function(product_list_query) 注册。

    Args:
        filters: 筛选条件，可为 JSON 字符串（含 page、page_size、product_type、keyword）或纯关键词。

    Returns:
        ToolResponse: 包含产品列表摘要与条数；未安装 agentscope 时抛出 RuntimeError。
    """
    if not _AGENTSCOPE_AVAILABLE or ToolResponse is None or TextBlock is None:
        raise RuntimeError("agentscope 未安装，无法返回 ToolResponse")
    params = _parse_filters(filters)
    page = int(params.pop("page", 1))
    page_size = int(params.pop("page_size", 10))
    product_type = params.get("product_type") or None
    keyword = params.get("keyword") or None
    result = query_product_list(
        page=page,
        page_size=page_size,
        product_type=product_type,
        keyword=keyword,
    )
    text = result["summary"]
    if result.get("products"):
        lines = []
        for i, p in enumerate(result["products"][:10], 1):
            name = p.get("name") or p.get("product_name") or p.get("id") or ""
            pid = p.get("id") or p.get("product_id") or ""
            lines.append(f"{i}. {name}（id: {pid}）")
        text += "\n\n" + "\n".join(lines)
        if result["total"] > 10:
            text += f"\n… 共 {result['total']} 条，仅展示前 10 条。"
    return ToolResponse(content=[TextBlock(type="text", text=text)])
