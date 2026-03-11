"""
Model Gateway 配置：从环境变量读取 LLM/Embedding/Reranker 内网地址与模型名。
配置化路由、超时与熔断参数。
"""
import os
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen3"
    temperature: float = 0.3
    max_tokens: int = 1000
    timeout_seconds: float = 60.0


@dataclass
class EmbeddingConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "bge-m3"
    timeout_seconds: float = 30.0


@dataclass
class RerankerConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "bge-reranker-large"
    timeout_seconds: float = 30.0


@dataclass
class GatewayConfig:
    """统一模型网关配置；未配置时 base_url 为空，调用方可做 mock/占位。"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    # 熔断：连续失败次数超过此值后进入熔断，熔断时长（秒）
    circuit_breaker_threshold: int = 5
    circuit_breaker_seconds: float = 60.0


def load_gateway_config() -> GatewayConfig:
    """从环境变量加载配置，与 .env.example 键一致。"""
    return GatewayConfig(
        llm=LLMConfig(
            base_url=os.getenv("LLM_BASE_URL", "").strip(),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            model=os.getenv("LLM_MODEL", "qwen3"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1000")),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        ),
        embedding=EmbeddingConfig(
            base_url=os.getenv("EMBEDDING_BASE_URL", "").strip(),
            api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
            model=os.getenv("EMBEDDING_MODEL", "bge-m3"),
            timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30")),
        ),
        reranker=RerankerConfig(
            base_url=os.getenv("RERANKER_BASE_URL", "").strip(),
            api_key=os.getenv("RERANKER_API_KEY", "").strip(),
            model=os.getenv("RERANKER_MODEL", "bge-reranker-large"),
            timeout_seconds=float(os.getenv("RERANKER_TIMEOUT_SECONDS", "30")),
        ),
        circuit_breaker_threshold=int(os.getenv("MODEL_GATEWAY_CB_THRESHOLD", "5")),
        circuit_breaker_seconds=float(os.getenv("MODEL_GATEWAY_CB_SECONDS", "60")),
    )
