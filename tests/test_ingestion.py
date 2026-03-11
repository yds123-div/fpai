# T032：ingestion 分块、投递、Worker 消费
import pytest

from ingestion.chunking import chunk_text


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short():
    text = "一段短文本"
    assert chunk_text(text) == [text]
    assert chunk_text(text, chunk_size=10) == [text]


def test_chunk_text_splits_by_paragraph():
    text = "第一段\n\n第二段\n\n第三段"
    chunks = chunk_text(text, chunk_size=100)
    assert len(chunks) >= 1
    assert "第一段" in chunks[0] or any("第一段" in c for c in chunks)
    assert all(len(c) <= 100 + 50 for c in chunks)


def test_chunk_text_long_paragraph():
    long_para = "a" * 1200
    chunks = chunk_text(long_para, chunk_size=500, overlap=50)
    assert len(chunks) >= 2
    assert sum(len(c) for c in chunks) >= 1000
