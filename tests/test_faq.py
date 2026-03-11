"""FAQ 智能体单元/集成测试：检索 search_faq、query_faq、faq_query 工具。"""
import pytest

from agents.faq.store import FAQHit, get_faq_by_ids, list_effective_faq
from agents.faq.retrieval import search_faq
from agents.faq.agent import query_faq, faq_query


def test_faq_hit_to_dict():
    h = FAQHit(id=1, question="什么是风险等级？", answer="风险等级用于衡量产品风险。", tags=["风险"])
    d = h.to_dict()
    assert d["id"] == 1
    assert "风险等级" in d["question"]
    assert d["tags"] == ["风险"]


def test_search_faq_empty_query():
    assert search_faq("") == []
    assert search_faq("   ") == []


def test_store_list_and_get_empty():
    """无 MySQL 或空表时 list_effective_faq / get_faq_by_ids 返回空。"""
    assert get_faq_by_ids([]) == []
    # list_effective_faq 在无 MySQL 时返回 []，有 MySQL 时可能非空
    eff = list_effective_faq()
    assert isinstance(eff, list)


def test_query_faq_no_hit():
    """无向量检索命中时返回 hit=False。"""
    r = query_faq("不存在的问题关键词xyz_nonexistent_faq_12345")
    assert r["hit"] is False
    assert r["answer"] == ""
    assert r["answer_blocks"] == []
    assert r["citations"] == []


def test_query_faq_structure():
    """query_faq 返回结构含 hit、answer、answer_blocks、citations、matches。"""
    r = query_faq("任意问题")
    assert "hit" in r and "answer" in r and "answer_blocks" in r
    assert "citations" in r and "matches" in r


@pytest.mark.integration
def test_search_faq_with_mysql_and_milvus():
    """MySQL + 同步到 Milvus 后，向量检索能返回回表结果。"""
    from pkg.mysql_client import is_configured, get_connection
    from agents.faq.sync import sync_faq_to_milvus
    if not is_configured():
        pytest.skip("MySQL 未配置，跳过集成测试")
    with get_connection() as conn:
        if conn is None:
            pytest.skip("无法获取连接")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO faq (question, answer) VALUES (%s, %s)",
                ("理财产品风险等级如何划分？", "风险等级一般分为 R1-R5 五档。"),
            )
            conn.commit()
    sync_faq_to_milvus()
    hits = search_faq("风险等级", top_k=2)
    assert isinstance(hits, list)
    for h in hits:
        assert isinstance(h, FAQHit)
        assert h.question and h.answer


def test_faq_query_tool_without_agentscope():
    """未安装 agentscope 时 faq_query 调用会抛 RuntimeError（因无法构造 ToolResponse）。"""
    import asyncio
    try:
        from agents.faq.agent import _AGENTSCOPE_AVAILABLE
        if _AGENTSCOPE_AVAILABLE:
            pytest.skip("agentscope 已安装，跳过本场景")
    except ImportError:
        pass
    async def _run():
        await faq_query("测试")
    with pytest.raises(RuntimeError):
        asyncio.run(_run())
