"""RAG 智能体单元测试：query_rag、rag_query 结构及无 agentscope 时行为。"""
import pytest

from agents.rag import query_rag, rag_query


def test_query_rag_empty_query():
    r = query_rag("")
    assert r["answer_blocks"] == []
    assert r["citations"] == []
    assert r["answer"] == ""

    r = query_rag("   ")
    assert "answer_blocks" in r and "citations" in r and "answer" in r


def test_query_rag_structure():
    r = query_rag("任意检索词", top_k=2)
    assert "answer_blocks" in r and "citations" in r and "answer" in r
    assert isinstance(r["answer_blocks"], list)
    assert isinstance(r["citations"], list)
    assert isinstance(r["answer"], str)


def test_rag_query_tool_without_agentscope():
    """未安装 agentscope 时 rag_query 调用会抛 RuntimeError。"""
    import asyncio
    try:
        from agents.rag.agent import _AGENTSCOPE_AVAILABLE
        if _AGENTSCOPE_AVAILABLE:
            pytest.skip("agentscope 已安装，跳过本场景")
    except ImportError:
        pass
    async def _run():
        await rag_query("测试")
    with pytest.raises(RuntimeError):
        asyncio.run(_run())
