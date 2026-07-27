"""
AkShare 数据源配置。

提供 AkShare 数据获取的配置管理，包括：
- 重试策略
- 限流控制
- 缓存配置
- 超时设置
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field, field_validator, ConfigDict


class AkShareConfig(BaseModel):
    """AkShare 配置类。
    
    使用 Pydantic 进行配置验证和类型检查。
    """
    
    # ========== 重试配置 ==========
    retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="最大重试次数（1-10）",
    )
    
    retry_initial_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="初始重试延迟（秒，0.1-10.0）",
    )
    
    retry_max_delay: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="最大重试延迟（秒，1.0-60.0）",
    )
    
    retry_backoff_factor: float = Field(
        default=2.0,
        ge=1.0,
        le=5.0,
        description="重试延迟倍增因子（1.0-5.0）",
    )
    
    # ========== 限流配置 ==========
    rate_limit_calls: int = Field(
        default=10,
        ge=1,
        le=100,
        description="限流：每个时间窗口的最大调用次数（1-100）",
    )
    
    rate_limit_period: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="限流：时间窗口大小（秒，0.1-60.0）",
    )
    
    # ========== 缓存配置 ==========
    cache_enabled: bool = Field(
        default=True,
        description="是否启用缓存",
    )
    
    cache_ttl_basic_info: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="基本信息缓存 TTL（秒，60-86400）",
    )
    
    cache_ttl_achievement: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="业绩数据缓存 TTL（秒，60-86400）",
    )
    
    cache_ttl_nav_data: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="净值数据缓存 TTL（秒，60-86400）",
    )
    
    cache_ttl_asset_allocation: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="资产配置缓存 TTL（秒，60-86400）",
    )
    
    cache_max_size: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="内存缓存最大条目数（100-10000）",
    )
    
    # ========== 超时配置 ==========
    timeout_default: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="默认超时时间（秒，1.0-60.0）",
    )
    
    timeout_nav_data: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        description="净值数据超时时间（秒，1.0-60.0）",
    )
    
    # ========== 并发控制 ==========
    concurrent_max: int = Field(
        default=3,
        ge=1,
        le=10,
        description="最大并发请求数（1-10）",
    )
    
    # ========== 数据降采样 ==========
    nav_data_max_points: int = Field(
        default=100,
        ge=50,
        le=500,
        description="净值数据最大点数（50-500）",
    )
    
    # ========== Redis 缓存配置（可选） ==========
    redis_cache_enabled: bool = Field(
        default=False,
        description="是否启用 Redis 缓存（需要配置 Redis）",
    )
    
    redis_cache_prefix: str = Field(
        default="akshare:",
        description="Redis 缓存键前缀",
    )
    
    # ========== 日志配置 ==========
    log_level: str = Field(
        default="INFO",
        description="日志级别（DEBUG/INFO/WARNING/ERROR）",
    )
    
    log_api_calls: bool = Field(
        default=True,
        description="是否记录 API 调用日志",
    )
    
    log_cache_hits: bool = Field(
        default=False,
        description="是否记录缓存命中日志（调试用）",
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别。"""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper
    
    @field_validator("retry_max_delay")
    @classmethod
    def validate_retry_delays(cls, v: float, info: Any) -> float:
        """验证重试延迟配置的合理性。"""
        if "retry_initial_delay" in info.data:
            initial = info.data["retry_initial_delay"]
            if v < initial:
                raise ValueError("retry_max_delay must be >= retry_initial_delay")
        return v
    
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",  # 禁止额外字段
    )


def load_akshare_config() -> AkShareConfig:
    """从环境变量加载 AkShare 配置。
    
    环境变量命名规则：AKSHARE_ + 配置项大写（用下划线分隔）
    
    示例：
        AKSHARE_RETRY_MAX_ATTEMPTS=5
        AKSHARE_CACHE_ENABLED=true
        AKSHARE_RATE_LIMIT_CALLS=20
    
    Returns:
        AkShareConfig 实例
    
    Example:
        >>> config = load_akshare_config()
        >>> print(config.retry_max_attempts)
        3
    """
    config_dict = {}
    
    # 从环境变量读取配置
    for field_name in AkShareConfig.model_fields.keys():
        env_name = f"AKSHARE_{field_name.upper()}"
        env_value = os.getenv(env_name)
        
        if env_value is not None:
            # 类型转换
            field_info = AkShareConfig.model_fields[field_name]
            field_type = field_info.annotation
            
            try:
                if field_type == bool:
                    config_dict[field_name] = env_value.lower() in ("true", "1", "yes", "on")
                elif field_type == int:
                    config_dict[field_name] = int(env_value)
                elif field_type == float:
                    config_dict[field_name] = float(env_value)
                else:
                    config_dict[field_name] = env_value
            except (ValueError, TypeError) as e:
                import logging
                logging.warning(f"Failed to parse {env_name}={env_value}: {e}")
    
    return AkShareConfig(**config_dict)


# 全局配置实例（单例）
_global_config: AkShareConfig | None = None


def get_akshare_config() -> AkShareConfig:
    """获取全局 AkShare 配置实例（单例模式）。
    
    Returns:
        AkShareConfig 实例
    
    Example:
        >>> config = get_akshare_config()
        >>> print(config.cache_enabled)
        True
    """
    global _global_config
    if _global_config is None:
        _global_config = load_akshare_config()
    return _global_config


def reload_akshare_config() -> AkShareConfig:
    """重新加载 AkShare 配置（用于配置热更新）。
    
    Returns:
        新的 AkShareConfig 实例
    
    Example:
        >>> config = reload_akshare_config()
        >>> print(config.retry_max_attempts)
        3
    """
    global _global_config
    _global_config = load_akshare_config()
    return _global_config


# 导出
__all__ = [
    "AkShareConfig",
    "load_akshare_config",
    "get_akshare_config",
    "reload_akshare_config",
]
