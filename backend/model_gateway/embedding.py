"""
Embedding 统一调用（BGE-M3/BGE-LARGE-ZH 等 OpenAI 兼容 /v1/embeddings）。
"""
from __future__ import annotations

from model_gateway.config import GatewayConfig, load_gateway_config
from model_gateway._circuit import is_open, record_failure, record_success
from model_gateway.llm import ModelGatewayError, ModelNotConfiguredError

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]


def _embed_sync(
    base_url: str,
    api_key: str,
    model: str,
    texts: list[str],
    timeout: float = 30.0,
) -> list[list[float]]:
    """同步调用 /v1/embeddings，返回每个 text 的向量。"""
    if not httpx:
        raise ModelGatewayError("httpx 未安装")
    url = base_url.rstrip("/") + "/v1/embeddings"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # 单条或 batch 取决于服务能力，此处按单条循环以兼容多数实现
    vectors = []
    for text in texts:
        payload = {"model": model, "input": text}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        emb = (data.get("data") or [{}])[0].get("embedding") or []
        vectors.append(emb)
    return vectors


def embed(
    texts: list[str],
    model: str | None = None,
    config: GatewayConfig | None = None,
) -> list[list[float]]:
    """
    Embedding 向量化；未配置 base_url 时抛出 ModelNotConfiguredError。
    熔断 key 为 "embedding"。
    """
    cfg = config or load_gateway_config()
    emb_cfg = cfg.embedding
    if not emb_cfg.base_url:
        raise ModelNotConfiguredError("EMBEDDING_BASE_URL 未配置")
    key = "embedding"
    if is_open(key):
        raise ModelGatewayError("Embedding 熔断中，请稍后重试")
    model_name = model or emb_cfg.model
    try:
        out = _embed_sync(
            emb_cfg.base_url,
            emb_cfg.api_key,
            model_name,
            texts,
            timeout=emb_cfg.timeout_seconds,
        )
        record_success(key)
        return out
    except Exception as e:
        record_failure(key, cfg.circuit_breaker_threshold, cfg.circuit_breaker_seconds)
        if isinstance(e, ModelGatewayError):
            raise
        raise ModelGatewayError(f"Embedding 调用失败: {e}") from e
