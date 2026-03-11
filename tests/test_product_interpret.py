"""产品解读智能体单元测试：query_product_interpret、product_interpret_query。"""
import pytest

from agents.product_interpret import query_product_interpret, product_interpret_query


def test_query_product_interpret_empty_id():
    r = query_product_interpret("")
    assert r["product"] is None
    assert r["answer"]
    assert "请提供产品 ID" in r["answer"] or "产品" in r["answer"]


def test_query_product_interpret_structure():
    """无对应产品时仍返回约定结构。"""
    r = query_product_interpret("nonexistent_id_xyz_123")
    assert "product" in r and "elements" in r and "highlights" in r and "risk_tips" in r and "answer" in r
    assert isinstance(r["highlights"], list)
    assert isinstance(r["risk_tips"], list)
    assert isinstance(r["answer"], str)


def test_query_product_interpret_with_retrieval_flag():
    r = query_product_interpret("any_id", use_retrieval=True, use_reagent=False)
    assert "highlights" in r and "risk_tips" in r


def test_product_interpret_query_tool_without_agentscope():
    """未安装 agentscope 时 product_interpret_query 调用会抛 RuntimeError。"""
    import asyncio
    try:
        from agents.product_interpret.agent import _AGENTSCOPE_AVAILABLE
        if _AGENTSCOPE_AVAILABLE:
            pytest.skip("agentscope 已安装，跳过本场景")
    except ImportError:
        pass
    async def _run():
        await product_interpret_query("id1")
    with pytest.raises(RuntimeError):
        asyncio.run(_run())
