"""
测试监控配置。

测试场景：
1. Counter 指标
2. Histogram 指标
3. AkShare 监控指标
4. Agent 监控指标
5. 装饰器功能
"""

import pytest
import asyncio
import time
from config.monitoring_config import (
    Counter,
    Histogram,
    AkShareMetrics,
    AgentMetrics,
    get_akshare_metrics,
    get_agent_metrics,
    monitor_akshare_api,
    monitor_agent_execution,
    print_monitoring_summary,
)


class TestCounter:
    """测试 Counter 指标。"""

    def test_counter_basic(self):
        """测试基本的计数功能。"""
        counter = Counter("test_counter", "Test counter")
        
        # 初始值为 0
        assert counter.get() == 0.0
        
        # 增加计数
        counter.inc()
        assert counter.get() == 1.0
        
        counter.inc(5.0)
        assert counter.get() == 6.0

    def test_counter_with_labels(self):
        """测试带标签的计数器。"""
        counter = Counter("test_counter", "Test counter", labels=["method", "status"])
        
        # 不同标签的计数独立
        counter.inc(method="GET", status="200")
        counter.inc(method="GET", status="200")
        counter.inc(method="POST", status="201")
        
        assert counter.get(method="GET", status="200") == 2.0
        assert counter.get(method="POST", status="201") == 1.0
        assert counter.get(method="GET", status="404") == 0.0

    def test_counter_reset(self):
        """测试重置计数器。"""
        counter = Counter("test_counter", "Test counter")
        
        counter.inc(10.0)
        assert counter.get() == 10.0
        
        counter.reset()
        assert counter.get() == 0.0


class TestHistogram:
    """测试 Histogram 指标。"""

    def test_histogram_basic(self):
        """测试基本的直方图功能。"""
        histogram = Histogram("test_histogram", "Test histogram")
        
        # 记录观测值
        histogram.observe(0.5)
        histogram.observe(1.5)
        histogram.observe(2.5)
        
        assert histogram.get_count() == 3
        assert histogram.get_sum() == 4.5

    def test_histogram_buckets(self):
        """测试直方图桶统计。"""
        histogram = Histogram(
            "test_histogram",
            "Test histogram",
            buckets=[1.0, 2.0, 5.0, 10.0],
        )
        
        # 记录观测值
        histogram.observe(0.5)
        histogram.observe(1.5)
        histogram.observe(3.0)
        histogram.observe(8.0)
        
        # 验证桶统计
        assert histogram.get_bucket(le=1.0) == 1  # 0.5
        assert histogram.get_bucket(le=2.0) == 2  # 0.5, 1.5
        assert histogram.get_bucket(le=5.0) == 3  # 0.5, 1.5, 3.0
        assert histogram.get_bucket(le=10.0) == 4  # 所有

    def test_histogram_with_labels(self):
        """测试带标签的直方图。"""
        histogram = Histogram("test_histogram", "Test histogram", labels=["method"])
        
        histogram.observe(1.0, method="GET")
        histogram.observe(2.0, method="GET")
        histogram.observe(3.0, method="POST")
        
        assert histogram.get_count(method="GET") == 2
        assert histogram.get_sum(method="GET") == 3.0
        assert histogram.get_count(method="POST") == 1
        assert histogram.get_sum(method="POST") == 3.0

    def test_histogram_reset(self):
        """测试重置直方图。"""
        histogram = Histogram("test_histogram", "Test histogram")
        
        histogram.observe(1.0)
        histogram.observe(2.0)
        assert histogram.get_count() == 2
        
        histogram.reset()
        assert histogram.get_count() == 0


class TestAkShareMetrics:
    """测试 AkShare 监控指标。"""

    def test_record_api_call_success(self):
        """测试记录成功的 API 调用。"""
        metrics = AkShareMetrics()
        
        metrics.record_api_call("test_api", 1.5, "success")
        
        assert metrics.api_calls_total.get(api_name="test_api", status="success") == 1.0
        assert metrics.api_duration_seconds.get_count(api_name="test_api") == 1
        assert metrics.api_duration_seconds.get_sum(api_name="test_api") == 1.5

    def test_record_api_call_timeout(self):
        """测试记录超时的 API 调用。"""
        metrics = AkShareMetrics()
        
        metrics.record_api_call("test_api", 0.0, "timeout")
        
        assert metrics.api_calls_total.get(api_name="test_api", status="timeout") == 1.0
        # 超时不记录耗时
        assert metrics.api_duration_seconds.get_count(api_name="test_api") == 0

    def test_record_api_call_error(self):
        """测试记录错误的 API 调用。"""
        metrics = AkShareMetrics()
        
        metrics.record_api_call("test_api", 0.0, "error")
        
        assert metrics.api_calls_total.get(api_name="test_api", status="error") == 1.0

    def test_record_cache_hit(self):
        """测试记录缓存命中。"""
        metrics = AkShareMetrics()
        
        metrics.record_cache_hit("basic_info")
        metrics.record_cache_hit("basic_info")
        
        assert metrics.cache_hits_total.get(cache_type="basic_info") == 2.0

    def test_record_cache_miss(self):
        """测试记录缓存未命中。"""
        metrics = AkShareMetrics()
        
        metrics.record_cache_miss("basic_info")
        
        assert metrics.cache_misses_total.get(cache_type="basic_info") == 1.0

    def test_get_cache_hit_rate(self):
        """测试获取缓存命中率。"""
        metrics = AkShareMetrics()
        
        # 初始命中率为 0
        assert metrics.get_cache_hit_rate("basic_info") == 0.0
        
        # 记录命中和未命中
        metrics.record_cache_hit("basic_info")
        metrics.record_cache_hit("basic_info")
        metrics.record_cache_hit("basic_info")
        metrics.record_cache_miss("basic_info")
        
        # 命中率 = 3 / 4 = 0.75
        assert metrics.get_cache_hit_rate("basic_info") == 0.75


class TestAgentMetrics:
    """测试 Agent 监控指标。"""

    def test_record_execution_success(self):
        """测试记录成功的 Agent 执行。"""
        metrics = AgentMetrics()
        
        metrics.record_execution("TestAgent", 2.5, "success")
        
        assert metrics.execution_total.get(agent_name="TestAgent", status="success") == 1.0
        assert metrics.execution_duration_seconds.get_count(agent_name="TestAgent", status="success") == 1
        assert metrics.execution_duration_seconds.get_sum(agent_name="TestAgent", status="success") == 2.5

    def test_record_execution_error(self):
        """测试记录错误的 Agent 执行。"""
        metrics = AgentMetrics()
        
        metrics.record_execution("TestAgent", 1.0, "error")
        
        assert metrics.execution_total.get(agent_name="TestAgent", status="error") == 1.0


class TestGlobalInstances:
    """测试全局实例。"""

    def test_get_akshare_metrics_singleton(self):
        """测试 AkShare 监控指标单例。"""
        metrics1 = get_akshare_metrics()
        metrics2 = get_akshare_metrics()
        
        assert metrics1 is metrics2

    def test_get_agent_metrics_singleton(self):
        """测试 Agent 监控指标单例。"""
        metrics1 = get_agent_metrics()
        metrics2 = get_agent_metrics()
        
        assert metrics1 is metrics2


class TestDecorators:
    """测试装饰器。"""

    @pytest.mark.asyncio
    async def test_monitor_akshare_api_success(self):
        """测试监控 AkShare API 装饰器（成功场景）。"""
        metrics = get_akshare_metrics()
        metrics.reset()
        
        @monitor_akshare_api("test_api")
        async def test_func():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await test_func()
        
        assert result == "success"
        assert metrics.api_calls_total.get(api_name="test_api", status="success") == 1.0
        assert metrics.api_duration_seconds.get_count(api_name="test_api") == 1

    @pytest.mark.asyncio
    async def test_monitor_akshare_api_error(self):
        """测试监控 AkShare API 装饰器（错误场景）。"""
        metrics = get_akshare_metrics()
        metrics.reset()
        
        @monitor_akshare_api("test_api")
        async def test_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await test_func()
        
        assert metrics.api_calls_total.get(api_name="test_api", status="error") == 1.0

    @pytest.mark.asyncio
    async def test_monitor_akshare_api_timeout(self):
        """测试监控 AkShare API 装饰器（超时场景）。"""
        metrics = get_akshare_metrics()
        metrics.reset()
        
        @monitor_akshare_api("test_api")
        async def test_func():
            raise TimeoutError("Test timeout")
        
        with pytest.raises(TimeoutError):
            await test_func()
        
        assert metrics.api_calls_total.get(api_name="test_api", status="timeout") == 1.0

    @pytest.mark.asyncio
    async def test_monitor_agent_execution_success(self):
        """测试监控 Agent 执行装饰器（成功场景）。"""
        metrics = get_agent_metrics()
        metrics.reset()
        
        @monitor_agent_execution("TestAgent")
        async def test_func():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await test_func()
        
        assert result == "success"
        assert metrics.execution_total.get(agent_name="TestAgent", status="success") == 1.0
        assert metrics.execution_duration_seconds.get_count(agent_name="TestAgent", status="success") == 1

    @pytest.mark.asyncio
    async def test_monitor_agent_execution_error(self):
        """测试监控 Agent 执行装饰器（错误场景）。"""
        metrics = get_agent_metrics()
        metrics.reset()
        
        @monitor_agent_execution("TestAgent")
        async def test_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await test_func()
        
        assert metrics.execution_total.get(agent_name="TestAgent", status="error") == 1.0

    def test_monitor_akshare_api_sync(self):
        """测试监控 AkShare API 装饰器（同步函数）。"""
        metrics = get_akshare_metrics()
        metrics.reset()
        
        @monitor_akshare_api("test_api")
        def test_func():
            time.sleep(0.1)
            return "success"
        
        result = test_func()
        
        assert result == "success"
        assert metrics.api_calls_total.get(api_name="test_api", status="success") == 1.0


class TestMonitoringSummary:
    """测试监控摘要。"""

    def test_print_monitoring_summary(self):
        """测试打印监控摘要（不应该抛出异常）。"""
        # 记录一些指标
        akshare_metrics = get_akshare_metrics()
        akshare_metrics.reset()
        akshare_metrics.record_api_call("test_api", 1.5, "success")
        akshare_metrics.record_cache_hit("basic_info")
        akshare_metrics.record_cache_miss("basic_info")
        
        agent_metrics = get_agent_metrics()
        agent_metrics.reset()
        agent_metrics.record_execution("TestAgent", 2.5, "success")
        
        # 不应该抛出异常
        print_monitoring_summary()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
