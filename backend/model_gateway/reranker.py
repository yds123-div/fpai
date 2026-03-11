"""
Reranker 统一调用（BGE-RERANKER-LARGE 等）。
常见为 query + documents 返回相关性分数或排序；接口因部署而异，此处采用占位 + 通用 POST 封装。
"""
from __future__ import annotations

from model_gateway.config import GatewayConfig, load_gateway_config
from model_gateway._circuit import is_open, record_failure, record_success
from model_gateway.llm import ModelGatewayError, ModelNotConfiguredError

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]


def _rerank_sync(
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    documents: list[str],
    timeout: float = 30.0,
) -> list[float]:
    """
    同步调用 Reranker；假定 OpenAI 兼容或 BGE reranker 风格：POST 含 query、documents，返回 scores。
    若服务为 /rerank 且返回 list of {index, score}，则按 index 排序后取 score 列表。
    """
    if not httpx:
        raise ModelGatewayError("httpx 未安装")
    # 常见路径
    url = base_url.rstrip("/") + "/v1/rerank"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "query": query, "documents": documents}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    # 兼容多种返回格式
    results = data.get("results") or data.get("data") or []
    if isinstance(results, list) and results and isinstance(results[0], dict):
        if "relevance_score" in results[0]:
            return [r.get("relevance_score", 0.0) for r in results]
        if "score" in results[0]:
            return [r.get("score", 0.0) for r in results]
        if "index" in results[0]:
            sorted_results = sorted(results, key=lambda x: x.get("index", 0))
            return [r.get("relevance_score", r.get("score", 0.0)) for r in sorted_results]
    if isinstance(results, list) and all(isinstance(x, (int, float)) for x in results):
        return [float(x) for x in results]
    return [0.0] * len(documents)


def rerank(
    query: str,
    documents: list[str],
    model: str | None = None,
    config: GatewayConfig | None = None,
) -> list[float]:
    """
    Reranker 精排：返回与 documents 一一对应的相关性分数（越高越相关）。
    未配置 base_url 时抛出 ModelNotConfiguredError。熔断 key 为 "reranker"。
    """
    cfg = config or load_gateway_config()
    rk_cfg = cfg.reranker
    if not rk_cfg.base_url:
        raise ModelNotConfiguredError("RERANKER_BASE_URL 未配置")
    key = "reranker"
    if is_open(key):
        raise ModelGatewayError("Reranker 熔断中，请稍后重试")
    model_name = model or rk_cfg.model
    try:
        out = _rerank_sync(
            rk_cfg.base_url,
            rk_cfg.api_key,
            model_name,
            query,
            documents,
            timeout=rk_cfg.timeout_seconds,
        )
        record_success(key)
        return out
    except Exception as e:
        record_failure(key, cfg.circuit_breaker_threshold, cfg.circuit_breaker_seconds)
        if isinstance(e, ModelGatewayError):
            raise
        raise ModelGatewayError(f"Reranker 调用失败: {e}") from e
