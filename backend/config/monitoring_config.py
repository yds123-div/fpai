"""
监控配置模块。

提供 Prometheus 指标和 AkShare 特定的监控功能。
基于 pkg.metrics 进行扩展。
"""

from __future__ import annotations

import time
from typing import Any, Callable
from functools import wraps

from pkg.metrics import get_metrics_collector, MetricsCollector


# ========== Prometheus 风格的指标（内存实现） ==========

class Counter:
    """计数器指标（只增不减）。"""
    
    def __init__(self, name: str, description: str, labels: list[str] | None = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self._values: dict[tuple, float] = {}
    
    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        """增加计数。"""
        key = self._make_key(label_values)
        self._values[key] = self._values.get(key, 0.0) + amount
    
    def get(self, **label_values: str) -> float:
        """获取当前值。"""
        key = self._make_key(label_values)
        return self._values.get(key, 0.0)
    
    def _make_key(self, label_values: dict[str, str]) -> tuple:
        """生成标签键。"""
        return tuple(sorted(label_values.items()))
    
    def reset(self) -> None:
        """重置计数器。"""
        self._values.clear()


class Histogram:
    """直方图指标（记录分布）。"""
    
    def __init__(
        self,
        name: str,
        description: str,
        labels: list[str] | None = None,
        buckets: list[float] | None = None,
    ):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._observations: dict[tuple, list[float]] = {}
    
    def observe(self, value: float, **label_values: str) -> None:
        """记录观测值。"""
        key = self._make_key(label_values)
        if key not in self._observations:
            self._observations[key] = []
        self._observations[key].append(value)
    
    def get_count(self, **label_values: str) -> int:
        """获取观测次数。"""
        key = self._make_key(label_values)
        return len(self._observations.get(key, []))
    
    def get_sum(self, **label_values: str) -> float:
        """获取观测值总和。"""
        key = self._make_key(label_values)
        return sum(self._observations.get(key, []))
    
    def get_bucket(self, le: float, **label_values: str) -> int:
        """获取小于等于指定值的观测次数。"""
        key = self._make_key(label_values)
        observations = self._observations.get(key, [])
        return sum(1 for v in observations if v <= le)
    
    def _make_key(self, label_values: dict[str, str]) -> tuple:
        """生成标签键。"""
        return tuple(sorted(label_values.items()))
    
    def reset(self) -> None:
        """重置直方图。"""
        self._observations.clear()


# ========== AkShare 监控指标 ==========

class AkShareMetrics:
    """AkShare 特定的监控指标。"""
    
    def __init__(self):
        # API 调用次数（按 API 名称和状态分类）
        self.api_calls_total = Counter(
            name="akshare_api_calls_total",
            description="Total number of AkShare API calls",
            labels=["api_name", "status"],  # status: success/timeout/error
        )
        
        # API 调用耗时（按 API 名称分类）
        self.api_duration_seconds = Histogram(
            name="akshare_api_duration_seconds",
            description="AkShare API call duration in seconds",
            labels=["api_name"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        )
        
        # 缓存命中次数
        self.cache_hits_total = Counter(
            name="cache_hits_total",
            description="Total number of cache hits",
            labels=["cache_type"],  # cache_type: basic_info/achievement/nav_data/asset_allocation
        )
        
        # 缓存未命中次数
        self.cache_misses_total = Counter(
            name="cache_misses_total",
            description="Total number of cache misses",
            labels=["cache_type"],
        )
    
    def record_api_call(self, api_name: str, duration: float, status: str) -> None:
        """记录 API 调用。
        
        Args:
            api_name: API 名称（如 "fund_individual_basic_info_xq"）
            duration: 调用耗时（秒）
            status: 状态（success/timeout/error）
        """
        self.api_calls_total.inc(api_name=api_name, status=status)
        if status == "success":
            self.api_duration_seconds.observe(duration, api_name=api_name)
    
    def record_cache_hit(self, cache_type: str) -> None:
        """记录缓存命中。
        
        Args:
            cache_type: 缓存类型（basic_info/achievement/nav_data/asset_allocation）
        """
        self.cache_hits_total.inc(cache_type=cache_type)
    
    def record_cache_miss(self, cache_type: str) -> None:
        """记录缓存未命中。
        
        Args:
            cache_type: 缓存类型
        """
        self.cache_misses_total.inc(cache_type=cache_type)
    
    def get_cache_hit_rate(self, cache_type: str) -> float:
        """获取缓存命中率。
        
        Args:
            cache_type: 缓存类型
        
        Returns:
            命中率（0.0-1.0）
        """
        hits = self.cache_hits_total.get(cache_type=cache_type)
        misses = self.cache_misses_total.get(cache_type=cache_type)
        total = hits + misses
        return hits / total if total > 0 else 0.0
    
    def reset(self) -> None:
        """重置所有指标。"""
        self.api_calls_total.reset()
        self.api_duration_seconds.reset()
        self.cache_hits_total.reset()
        self.cache_misses_total.reset()


class AgentMetrics:
    """Agent 执行监控指标。"""
    
    def __init__(self):
        # Agent 执行耗时
        self.execution_duration_seconds = Histogram(
            name="agent_execution_duration_seconds",
            description="Agent execution duration in seconds",
            labels=["agent_name", "status"],  # status: success/error
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        )
        
        # Agent 执行次数
        self.execution_total = Counter(
            name="agent_execution_total",
            description="Total number of agent executions",
            labels=["agent_name", "status"],
        )
    
    def record_execution(self, agent_name: str, duration: float, status: str) -> None:
        """记录 Agent 执行。
        
        Args:
            agent_name: Agent 名称（如 "ProductInterpretAgent"）
            duration: 执行耗时（秒）
            status: 状态（success/error）
        """
        self.execution_total.inc(agent_name=agent_name, status=status)
        self.execution_duration_seconds.observe(duration, agent_name=agent_name, status=status)
    
    def reset(self) -> None:
        """重置所有指标。"""
        self.execution_duration_seconds.reset()
        self.execution_total.reset()


# ========== 全局监控实例 ==========

_akshare_metrics: AkShareMetrics | None = None
_agent_metrics: AgentMetrics | None = None


def get_akshare_metrics() -> AkShareMetrics:
    """获取 AkShare 监控指标实例（单例）。"""
    global _akshare_metrics
    if _akshare_metrics is None:
        _akshare_metrics = AkShareMetrics()
    return _akshare_metrics


def get_agent_metrics() -> AgentMetrics:
    """获取 Agent 监控指标实例（单例）。"""
    global _agent_metrics
    if _agent_metrics is None:
        _agent_metrics = AgentMetrics()
    return _agent_metrics


# ========== 装饰器 ==========

def monitor_akshare_api(api_name: str) -> Callable:
    """监控 AkShare API 调用的装饰器。
    
    Args:
        api_name: API 名称
    
    Example:
        >>> @monitor_akshare_api("fund_individual_basic_info_xq")
        ... async def get_basic_info(symbol: str):
        ...     # API 调用逻辑
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = get_akshare_metrics()
            collector = get_metrics_collector()
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # 记录成功
                metrics.record_api_call(api_name, duration, "success")
                collector.record_api_success(api_name, duration)
                
                return result
            except TimeoutError:
                # 记录超时
                metrics.record_api_call(api_name, 0.0, "timeout")
                collector.record_api_timeout(api_name)
                raise
            except Exception:
                # 记录错误
                metrics.record_api_call(api_name, 0.0, "error")
                collector.record_api_error(api_name)
                raise
        
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = get_akshare_metrics()
            collector = get_metrics_collector()
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # 记录成功
                metrics.record_api_call(api_name, duration, "success")
                collector.record_api_success(api_name, duration)
                
                return result
            except TimeoutError:
                # 记录超时
                metrics.record_api_call(api_name, 0.0, "timeout")
                collector.record_api_timeout(api_name)
                raise
            except Exception:
                # 记录错误
                metrics.record_api_call(api_name, 0.0, "error")
                collector.record_api_error(api_name)
                raise
        
        # 根据函数类型选择包装器
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def monitor_agent_execution(agent_name: str) -> Callable:
    """监控 Agent 执行的装饰器。
    
    Args:
        agent_name: Agent 名称
    
    Example:
        >>> @monitor_agent_execution("ProductInterpretAgent")
        ... async def run(self, question: str, ctx: AgentRunContext):
        ...     # Agent 执行逻辑
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = get_agent_metrics()
            collector = get_metrics_collector()
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # 记录成功
                metrics.record_execution(agent_name, duration, "success")
                collector.record_module_duration(f"agent.{agent_name}", duration)
                
                return result
            except Exception:
                duration = time.time() - start_time
                
                # 记录错误
                metrics.record_execution(agent_name, duration, "error")
                collector.record_module_duration(f"agent.{agent_name}.error", duration)
                
                raise
        
        return wrapper
    
    return decorator


# ========== 监控报告 ==========

def print_monitoring_summary() -> None:
    """打印监控摘要。"""
    import logging
    logger = logging.getLogger(__name__)
    
    akshare_metrics = get_akshare_metrics()
    agent_metrics = get_agent_metrics()
    
    logger.info("=" * 80)
    logger.info("监控指标摘要")
    logger.info("=" * 80)
    
    # AkShare API 调用统计
    logger.info("\n【AkShare API 调用】")
    api_names = set()
    for key in akshare_metrics.api_calls_total._values.keys():
        if key:
            api_names.add(key[0][1])  # (('api_name', 'xxx'), ('status', 'yyy'))
    
    for api_name in sorted(api_names):
        success = akshare_metrics.api_calls_total.get(api_name=api_name, status="success")
        timeout = akshare_metrics.api_calls_total.get(api_name=api_name, status="timeout")
        error = akshare_metrics.api_calls_total.get(api_name=api_name, status="error")
        total = success + timeout + error
        
        if total > 0:
            count = akshare_metrics.api_duration_seconds.get_count(api_name=api_name)
            if count > 0:
                avg_duration = akshare_metrics.api_duration_seconds.get_sum(api_name=api_name) / count
                logger.info(f"  {api_name}:")
                logger.info(f"    调用次数: {total} (成功: {success}, 超时: {timeout}, 错误: {error})")
                logger.info(f"    平均耗时: {avg_duration:.3f}s")
    
    # 缓存统计
    logger.info("\n【缓存统计】")
    cache_types = ["basic_info", "achievement", "nav_data", "asset_allocation"]
    for cache_type in cache_types:
        hits = akshare_metrics.cache_hits_total.get(cache_type=cache_type)
        misses = akshare_metrics.cache_misses_total.get(cache_type=cache_type)
        total = hits + misses
        
        if total > 0:
            hit_rate = akshare_metrics.get_cache_hit_rate(cache_type)
            logger.info(f"  {cache_type}:")
            logger.info(f"    命中: {hits}, 未命中: {misses}, 命中率: {hit_rate * 100:.2f}%")
    
    # Agent 执行统计
    logger.info("\n【Agent 执行】")
    agent_names = set()
    for key in agent_metrics.execution_total._values.keys():
        if key:
            agent_names.add(key[0][1])  # (('agent_name', 'xxx'), ('status', 'yyy'))
    
    for agent_name in sorted(agent_names):
        success = agent_metrics.execution_total.get(agent_name=agent_name, status="success")
        error = agent_metrics.execution_total.get(agent_name=agent_name, status="error")
        total = success + error
        
        if total > 0:
            count_success = agent_metrics.execution_duration_seconds.get_count(
                agent_name=agent_name, status="success"
            )
            if count_success > 0:
                avg_duration = agent_metrics.execution_duration_seconds.get_sum(
                    agent_name=agent_name, status="success"
                ) / count_success
                logger.info(f"  {agent_name}:")
                logger.info(f"    执行次数: {total} (成功: {success}, 错误: {error})")
                logger.info(f"    平均耗时: {avg_duration:.3f}s")
    
    logger.info("=" * 80)


# 导出
__all__ = [
    "Counter",
    "Histogram",
    "AkShareMetrics",
    "AgentMetrics",
    "get_akshare_metrics",
    "get_agent_metrics",
    "monitor_akshare_api",
    "monitor_agent_execution",
    "print_monitoring_summary",
]
