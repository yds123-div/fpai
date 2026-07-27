# -*- coding: utf-8 -*-
"""
性能监控指标收集模块

提供 API 调用、LLM 调用等关键路径的性能指标收集：
- 平均耗时 / P95 / P99
- 超时率
- Token 统计
- 首 Token 延迟
"""

from __future__ import annotations

import time
import logging
from typing import Any
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class APIMetrics:
    """API 调用指标"""
    name: str
    durations: list[float] = field(default_factory=list)
    timeout_count: int = 0
    success_count: int = 0
    error_count: int = 0
    
    def record_success(self, duration: float) -> None:
        """记录成功调用"""
        self.durations.append(duration)
        self.success_count += 1
    
    def record_timeout(self) -> None:
        """记录超时"""
        self.timeout_count += 1
    
    def record_error(self) -> None:
        """记录错误"""
        self.error_count += 1
    
    @property
    def avg_duration(self) -> float:
        """平均耗时"""
        return sum(self.durations) / len(self.durations) if self.durations else 0.0
    
    @property
    def p95_duration(self) -> float:
        """P95 耗时"""
        if not self.durations:
            return 0.0
        sorted_durations = sorted(self.durations)
        idx = int(len(sorted_durations) * 0.95)
        return sorted_durations[idx] if idx < len(sorted_durations) else sorted_durations[-1]
    
    @property
    def p99_duration(self) -> float:
        """P99 耗时"""
        if not self.durations:
            return 0.0
        sorted_durations = sorted(self.durations)
        idx = int(len(sorted_durations) * 0.99)
        return sorted_durations[idx] if idx < len(sorted_durations) else sorted_durations[-1]
    
    @property
    def timeout_rate(self) -> float:
        """超时率"""
        total = self.success_count + self.timeout_count + self.error_count
        return self.timeout_count / total if total > 0 else 0.0
    
    def summary(self) -> dict[str, Any]:
        """生成摘要"""
        return {
            "name": self.name,
            "total_calls": self.success_count + self.timeout_count + self.error_count,
            "success_count": self.success_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "timeout_rate": f"{self.timeout_rate * 100:.2f}%",
            "avg_duration": f"{self.avg_duration:.3f}s",
            "p95_duration": f"{self.p95_duration:.3f}s",
            "p99_duration": f"{self.p99_duration:.3f}s",
        }


@dataclass
class LLMMetrics:
    """LLM 调用指标"""
    name: str
    input_tokens: list[int] = field(default_factory=list)
    output_tokens: list[int] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    first_token_latencies: list[float] = field(default_factory=list)
    
    def record(
        self,
        duration: float,
        input_token: int,
        output_token: int,
        first_token_latency: float | None = None,
    ) -> None:
        """记录 LLM 调用"""
        self.durations.append(duration)
        self.input_tokens.append(input_token)
        self.output_tokens.append(output_token)
        if first_token_latency is not None:
            self.first_token_latencies.append(first_token_latency)
    
    @property
    def avg_input_tokens(self) -> float:
        """平均输入 tokens"""
        return sum(self.input_tokens) / len(self.input_tokens) if self.input_tokens else 0.0
    
    @property
    def avg_output_tokens(self) -> float:
        """平均输出 tokens"""
        return sum(self.output_tokens) / len(self.output_tokens) if self.output_tokens else 0.0
    
    @property
    def avg_duration(self) -> float:
        """平均耗时"""
        return sum(self.durations) / len(self.durations) if self.durations else 0.0
    
    @property
    def avg_first_token_latency(self) -> float:
        """平均首 token 延迟"""
        return sum(self.first_token_latencies) / len(self.first_token_latencies) if self.first_token_latencies else 0.0
    
    def summary(self) -> dict[str, Any]:
        """生成摘要"""
        return {
            "name": self.name,
            "total_calls": len(self.durations),
            "avg_duration": f"{self.avg_duration:.3f}s",
            "avg_input_tokens": f"{self.avg_input_tokens:.0f}",
            "avg_output_tokens": f"{self.avg_output_tokens:.0f}",
            "avg_first_token_latency": f"{self.avg_first_token_latency:.3f}s",
        }


@dataclass
class ModuleMetrics:
    """模块级别指标（用于识别瓶颈）"""
    name: str
    durations: list[float] = field(default_factory=list)
    
    def record(self, duration: float) -> None:
        """记录模块耗时"""
        self.durations.append(duration)
    
    @property
    def avg_duration(self) -> float:
        """平均耗时"""
        return sum(self.durations) / len(self.durations) if self.durations else 0.0
    
    @property
    def max_duration(self) -> float:
        """最大耗时"""
        return max(self.durations) if self.durations else 0.0
    
    @property
    def total_duration(self) -> float:
        """总耗时"""
        return sum(self.durations)
    
    def summary(self) -> dict[str, Any]:
        """生成摘要"""
        return {
            "name": self.name,
            "total_calls": len(self.durations),
            "avg_duration": f"{self.avg_duration:.3f}s",
            "max_duration": f"{self.max_duration:.3f}s",
            "total_duration": f"{self.total_duration:.3f}s",
        }


class MetricsCollector:
    """全局指标收集器"""
    
    def __init__(self) -> None:
        self.api_metrics: dict[str, APIMetrics] = defaultdict(lambda: APIMetrics(name=""))
        self.llm_metrics: dict[str, LLMMetrics] = defaultdict(lambda: LLMMetrics(name=""))
        self.module_metrics: dict[str, ModuleMetrics] = defaultdict(lambda: ModuleMetrics(name=""))
    
    def record_api_success(self, api_name: str, duration: float) -> None:
        """记录 API 成功调用"""
        if api_name not in self.api_metrics:
            self.api_metrics[api_name] = APIMetrics(name=api_name)
        self.api_metrics[api_name].record_success(duration)
    
    def record_api_timeout(self, api_name: str) -> None:
        """记录 API 超时"""
        if api_name not in self.api_metrics:
            self.api_metrics[api_name] = APIMetrics(name=api_name)
        self.api_metrics[api_name].record_timeout()
    
    def record_api_error(self, api_name: str) -> None:
        """记录 API 错误"""
        if api_name not in self.api_metrics:
            self.api_metrics[api_name] = APIMetrics(name=api_name)
        self.api_metrics[api_name].record_error()
    
    def record_llm_call(
        self,
        llm_name: str,
        duration: float,
        input_tokens: int,
        output_tokens: int,
        first_token_latency: float | None = None,
    ) -> None:
        """记录 LLM 调用"""
        if llm_name not in self.llm_metrics:
            self.llm_metrics[llm_name] = LLMMetrics(name=llm_name)
        self.llm_metrics[llm_name].record(duration, input_tokens, output_tokens, first_token_latency)
    
    def record_module_duration(self, module_name: str, duration: float) -> None:
        """记录模块耗时"""
        if module_name not in self.module_metrics:
            self.module_metrics[module_name] = ModuleMetrics(name=module_name)
        self.module_metrics[module_name].record(duration)
    
    def get_slowest_module(self) -> str | None:
        """获取最慢的模块"""
        if not self.module_metrics:
            return None
        slowest = max(self.module_metrics.values(), key=lambda m: m.avg_duration)
        return slowest.name
    
    def print_summary(self) -> None:
        """打印性能摘要"""
        logger.info("=" * 80)
        logger.info("性能监控摘要")
        logger.info("=" * 80)
        
        if self.api_metrics:
            logger.info("\n【API 调用指标】")
            for api_name, metrics in sorted(self.api_metrics.items()):
                summary = metrics.summary()
                logger.info(f"  {api_name}:")
                logger.info(f"    调用次数: {summary['total_calls']} (成功: {summary['success_count']}, 超时: {summary['timeout_count']}, 错误: {summary['error_count']})")
                logger.info(f"    超时率: {summary['timeout_rate']}")
                logger.info(f"    平均耗时: {summary['avg_duration']}, P95: {summary['p95_duration']}, P99: {summary['p99_duration']}")
        
        if self.llm_metrics:
            logger.info("\n【LLM 调用指标】")
            for llm_name, metrics in sorted(self.llm_metrics.items()):
                summary = metrics.summary()
                logger.info(f"  {llm_name}:")
                logger.info(f"    调用次数: {summary['total_calls']}")
                logger.info(f"    平均耗时: {summary['avg_duration']}")
                logger.info(f"    平均输入 tokens: {summary['avg_input_tokens']}")
                logger.info(f"    平均输出 tokens: {summary['avg_output_tokens']}")
                logger.info(f"    平均首 token 延迟: {summary['avg_first_token_latency']}")
        
        if self.module_metrics:
            logger.info("\n【模块耗时指标】")
            # 按平均耗时排序
            sorted_modules = sorted(self.module_metrics.values(), key=lambda m: m.avg_duration, reverse=True)
            for metrics in sorted_modules:
                summary = metrics.summary()
                logger.info(f"  {metrics.name}:")
                logger.info(f"    调用次数: {summary['total_calls']}")
                logger.info(f"    平均耗时: {summary['avg_duration']}, 最大耗时: {summary['max_duration']}")
            
            slowest = self.get_slowest_module()
            if slowest:
                logger.info(f"\n  ⚠️  最慢模块: {slowest}")
        
        logger.info("=" * 80)
    
    def reset(self) -> None:
        """重置所有指标"""
        self.api_metrics.clear()
        self.llm_metrics.clear()
        self.module_metrics.clear()


# 全局单例
_global_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    return _global_collector


class Timer:
    """计时器上下文管理器"""
    
    def __init__(self, name: str, collector: MetricsCollector | None = None):
        self.name = name
        self.collector = collector or get_metrics_collector()
        self.start_time: float = 0.0
        self.duration: float = 0.0
    
    def __enter__(self) -> Timer:
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.duration = time.time() - self.start_time
        self.collector.record_module_duration(self.name, self.duration)
        logger.info(f"[PERF] {self.name} - 耗时: {self.duration:.3f}s")
