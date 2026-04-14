# -*- coding: utf-8 -*-
"""
性能监控模块测试
"""

import pytest
from pkg.metrics import (
    APIMetrics,
    LLMMetrics,
    ModuleMetrics,
    MetricsCollector,
    Timer,
)


def test_api_metrics():
    """测试 API 指标收集"""
    metrics = APIMetrics(name="test_api")
    
    # 记录成功调用
    metrics.record_success(0.5)
    metrics.record_success(1.0)
    metrics.record_success(1.5)
    
    # 记录超时
    metrics.record_timeout()
    
    # 验证统计
    assert metrics.success_count == 3
    assert metrics.timeout_count == 1
    assert metrics.avg_duration == 1.0
    assert metrics.timeout_rate == 0.25
    
    # 验证 P95
    assert metrics.p95_duration == 1.5


def test_llm_metrics():
    """测试 LLM 指标收集"""
    metrics = LLMMetrics(name="test_llm")
    
    # 记录调用
    metrics.record(duration=10.0, input_token=1000, output_token=500, first_token_latency=2.0)
    metrics.record(duration=15.0, input_token=1500, output_token=800, first_token_latency=3.0)
    
    # 验证统计
    assert len(metrics.durations) == 2
    assert metrics.avg_duration == 12.5
    assert metrics.avg_input_tokens == 1250.0
    assert metrics.avg_output_tokens == 650.0
    assert metrics.avg_first_token_latency == 2.5


def test_module_metrics():
    """测试模块指标收集"""
    metrics = ModuleMetrics(name="test_module")
    
    # 记录耗时
    metrics.record(1.0)
    metrics.record(2.0)
    metrics.record(3.0)
    
    # 验证统计
    assert metrics.avg_duration == 2.0
    assert metrics.max_duration == 3.0
    assert metrics.total_duration == 6.0


def test_metrics_collector():
    """测试指标收集器"""
    collector = MetricsCollector()
    
    # 记录 API 调用
    collector.record_api_success("api1", 0.5)
    collector.record_api_success("api1", 1.0)
    collector.record_api_timeout("api1")
    
    # 记录 LLM 调用
    collector.record_llm_call("llm1", 10.0, 1000, 500, 2.0)
    
    # 记录模块耗时
    collector.record_module_duration("module1", 5.0)
    collector.record_module_duration("module2", 10.0)
    
    # 验证收集
    assert "api1" in collector.api_metrics
    assert "llm1" in collector.llm_metrics
    assert "module1" in collector.module_metrics
    assert "module2" in collector.module_metrics
    
    # 验证最慢模块
    slowest = collector.get_slowest_module()
    assert slowest == "module2"
    
    # 打印摘要（不应抛异常）
    collector.print_summary()


def test_timer_context():
    """测试计时器上下文管理器"""
    collector = MetricsCollector()
    
    with Timer("test_operation", collector) as timer:
        import time
        time.sleep(0.1)
    
    # 验证记录
    assert "test_operation" in collector.module_metrics
    assert timer.duration >= 0.1


@pytest.mark.asyncio
async def test_metrics_in_async():
    """测试在异步环境中使用指标收集"""
    import asyncio
    from pkg.metrics import get_metrics_collector
    
    collector = get_metrics_collector()
    
    async def mock_api_call():
        await asyncio.sleep(0.1)
        return "result"
    
    # 模拟 API 调用
    import time
    start = time.time()
    result = await mock_api_call()
    duration = time.time() - start
    
    collector.record_api_success("mock_api", duration)
    
    # 验证
    assert "mock_api" in collector.api_metrics
    assert collector.api_metrics["mock_api"].success_count == 1
    assert collector.api_metrics["mock_api"].avg_duration >= 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
