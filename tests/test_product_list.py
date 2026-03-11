"""产品列表查询智能体单元测试：query_product_list、product_list_query 及路由接入。"""
import pytest

from agents.product_list import query_product_list, product_list_query


def test_query_product_list_structure():
    r = query_product_list(page=1, page_size=5)
    assert "products" in r and "total" in r and "summary" in r
    assert isinstance(r["products"], list)
    assert isinstance(r["total"], int)
    assert isinstance(r["summary"], str)


def test_query_product_list_pagination():
    r = query_product_list(page=2, page_size=3)
    assert r["total"] >= 0
    assert len(r["products"]) <= 3


def test_parse_filters_via_product_list_query():
    """filters 为空时仍可调用，返回摘要。"""
    r = query_product_list(page=1, page_size=10)
    assert r["summary"]


def test_product_list_query_tool_without_agentscope():
    """未安装 agentscope 时 product_list_query 调用会抛 RuntimeError。"""
    import asyncio
    try:
        from agents.product_list.agent import _AGENTSCOPE_AVAILABLE
        if _AGENTSCOPE_AVAILABLE:
            pytest.skip("agentscope 已安装，跳过本场景")
    except ImportError:
        pass
    async def _run():
        await product_list_query("")
    with pytest.raises(RuntimeError):
        asyncio.run(_run())
