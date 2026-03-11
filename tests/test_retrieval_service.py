"""retrieval.service 单元测试：retrieve、generate_answer、权限过滤；mock embed/Milvus/rerank/llm."""
import pytest

from retrieval.types import Citation, RetrieveResult, GenerateAnswerResult
from retrieval.service import retrieve, generate_answer


def test_retrieve_empty_when_embed_not_configured(monkeypatch):
    """Embed 未配置时返回空 chunks/scores/citations。"""
    from model_gateway.llm import ModelNotConfiguredError
    def _raise(*a, **k):
        raise ModelNotConfiguredError("embed")
    monkeypatch.setattr("retrieval.service.embed", _raise)
    r = retrieve("query", top_k=5)
    assert r.chunks == []
    assert r.scores == []
    assert r.citations == []


def test_retrieve_empty_when_embed_returns_empty(monkeypatch):
    """embed 返回空向量时返回空结果。"""
    monkeypatch.setattr("retrieval.service.embed", lambda x: [])
    r = retrieve("query", top_k=5)
    assert r.chunks == [] and r.scores == [] and r.citations == []


def test_retrieve_permission_filter_and_rerank(monkeypatch):
    """正常链路：embed → search_with_filter(带 permission 过滤) → rerank → 返回 chunks/scores/citations。"""
    monkeypatch.setattr("retrieval.service.embed", lambda texts: [[0.1] * 8])
    mock_hits = [
        {"id": "1", "distance": 0.5, "entity": {"doc_id": "d1", "source": "s1", "chunk_text": "text one"}},
        {"id": "2", "distance": 0.4, "entity": {"doc_id": "d2", "source": "s2", "chunk_text": "text two"}},
    ]
    def _search(query_vectors, filter_expr=None, top_k=10, output_fields=None):
        assert query_vectors == [[0.1] * 8]
        assert 'permission_tag' in (filter_expr or "")
        assert "pool1" in (filter_expr or "") and "pool2" in (filter_expr or "")
        return [mock_hits]
    monkeypatch.setattr("retrieval.service.search_with_filter", _search)
    monkeypatch.setattr("retrieval.service.rerank", lambda q, docs: [0.9, 0.8])
    r = retrieve(
        "q",
        top_k=2,
        permission_context={"permission_tags": ["pool1", "pool2"]},
        use_reranker=True,
    )
    assert len(r.chunks) == 2
    assert len(r.scores) == 2
    assert len(r.citations) == 2
    assert r.chunks[0]["doc_id"] == "d1" and r.chunks[0]["chunk_text"] == "text one"
    assert r.citations[0].doc_id == "d1" and r.citations[0].source == "s1"
    assert r.scores[0] == 0.9 and r.scores[1] == 0.8


def test_retrieve_no_reranker(monkeypatch):
    """use_reranker=False 时不做 rerank，按 Milvus 顺序返回。"""
    monkeypatch.setattr("retrieval.service.embed", lambda texts: [[0.1] * 8])
    mock_hits = [
        {"id": "1", "distance": 0.9, "entity": {"doc_id": "d1", "source": "s1", "chunk_text": "a"}},
    ]
    monkeypatch.setattr("retrieval.service.search_with_filter", lambda *a, **k: [mock_hits])
    r = retrieve("q", top_k=5, use_reranker=False)
    assert len(r.chunks) == 1 and r.chunks[0]["doc_id"] == "d1"
    assert r.scores[0] == 0.9


def test_retrieve_reranker_not_configured_fallback(monkeypatch):
    """Reranker 未配置时降级为按 Milvus 顺序取 top_k。"""
    from model_gateway.llm import ModelNotConfiguredError
    monkeypatch.setattr("retrieval.service.embed", lambda texts: [[0.1] * 8])
    mock_hits = [
        {"id": "1", "distance": 0.5, "entity": {"doc_id": "d1", "source": "s1", "chunk_text": "x"}},
        {"id": "2", "distance": 0.4, "entity": {"doc_id": "d2", "source": "s2", "chunk_text": "y"}},
    ]
    monkeypatch.setattr("retrieval.service.search_with_filter", lambda *a, **k: [mock_hits])
    monkeypatch.setattr("retrieval.service.rerank", lambda *a, **k: (_ for _ in ()).throw(ModelNotConfiguredError("rerank")))
    r = retrieve("q", top_k=2, use_reranker=True)
    assert len(r.chunks) == 2
    assert r.scores[0] == 0.5 and r.scores[1] == 0.4


def test_permission_context_product_pool_ids(monkeypatch):
    """permission_context 支持 product_pool_ids 别名。"""
    monkeypatch.setattr("retrieval.service.embed", lambda texts: [[0.1] * 8])
    seen_filter = []
    def _search(query_vectors, filter_expr=None, **kw):
        seen_filter.append(filter_expr)
        return [[]]
    monkeypatch.setattr("retrieval.service.search_with_filter", _search)
    retrieve("q", top_k=5, permission_context={"product_pool_ids": ["A", "B"]})
    assert len(seen_filter) == 1 and "A" in (seen_filter[0] or "") and "B" in (seen_filter[0] or "")


def test_generate_answer_empty_chunks():
    """无 chunks 时返回空 answer_blocks 与空 citations。"""
    out = generate_answer("query", [])
    assert out.answer_blocks == [""]
    assert out.citations == []


def test_generate_answer_llm_mock(monkeypatch):
    """有 chunks 时组 prompt 调 LLM，返回 answer_blocks 与 citations。"""
    monkeypatch.setattr("retrieval.service.llm_chat", lambda msgs: "Generated answer here.")
    chunks = [
        {"doc_id": "d1", "source": "s1", "chunk_text": "chunk one content"},
    ]
    cites = [Citation(doc_id="d1", source="s1", chunk_text="chunk one content", score=0.9)]
    out = generate_answer("user question", chunks, citations=cites)
    assert out.answer_blocks == ["Generated answer here."]
    assert len(out.citations) == 1 and out.citations[0].doc_id == "d1"


def test_generate_answer_llm_not_configured(monkeypatch):
    """LLM 未配置时返回占位文案。"""
    from model_gateway.llm import ModelNotConfiguredError
    monkeypatch.setattr("retrieval.service.llm_chat", lambda msgs: (_ for _ in ()).throw(ModelNotConfiguredError("llm")))
    out = generate_answer("q", [{"doc_id": "d1", "source": "s1", "chunk_text": "x"}])
    assert any("未配置" in b for b in out.answer_blocks)
    assert len(out.citations) == 1
