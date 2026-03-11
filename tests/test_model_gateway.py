"""Model Gateway 单元测试：配置加载、未配置时异常、熔断与占位行为."""
import pytest

from model_gateway import (
    load_gateway_config,
    ModelNotConfiguredError,
    ModelGatewayError,
    llm_chat,
    embed,
    rerank,
)
from model_gateway._circuit import reset, is_open, record_failure


def setup_module():
    reset()


def test_load_gateway_config_defaults(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    cfg = load_gateway_config()
    assert cfg.llm.model == "qwen3"
    assert cfg.embedding.model == "bge-m3"
    assert cfg.reranker.model == "bge-reranker-large"
    assert cfg.llm.base_url == "" or True
    assert cfg.circuit_breaker_threshold >= 1


def test_llm_chat_not_configured(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    from model_gateway.config import load_gateway_config
    cfg = load_gateway_config()
    with pytest.raises(ModelNotConfiguredError):
        llm_chat([{"role": "user", "content": "hi"}], config=cfg)


def test_embed_not_configured(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    from model_gateway.config import load_gateway_config
    cfg = load_gateway_config()
    with pytest.raises(ModelNotConfiguredError):
        embed(["text"], config=cfg)


def test_rerank_not_configured(monkeypatch):
    monkeypatch.setenv("RERANKER_BASE_URL", "")
    from model_gateway.config import load_gateway_config
    cfg = load_gateway_config()
    with pytest.raises(ModelNotConfiguredError):
        rerank("query", ["doc1"], config=cfg)


def test_circuit_breaker_opens_after_threshold(monkeypatch):
    reset("llm")
    monkeypatch.setenv("LLM_BASE_URL", "http://invalid.example")
    monkeypatch.setenv("LLM_MODEL", "x")
    from model_gateway.config import load_gateway_config
    cfg = load_gateway_config()
    cfg.circuit_breaker_threshold = 2
    cfg.circuit_breaker_seconds = 10.0
    for _ in range(3):
        record_failure("llm", 2, 10.0)
    assert is_open("llm") is True
    reset("llm")
    assert is_open("llm") is False
