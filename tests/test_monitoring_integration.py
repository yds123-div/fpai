"""
监控集成测试。

验证监控系统与 AkShareClient 和 Agent 的集成。
"""

import pytest

from config.monitoring_config import get_akshare_metrics, get_agent_metrics, print_monitoring_summary
from pkg.akshare_client import AkShareClient


class TestMonitoringIntegration:
    """测试监控集成。"""
    
    @pytest.mark.asyncio
    async def test_akshare_client_cache_monitoring(self):
        """测试 AkShareClient 缓存监控集成。"""
        # 重置指标
        metrics = get_akshare_metrics()
        metrics.reset()
        
        # 创建客户端
        client = AkShareClient(enable_cache=True, cache_ttl=60)
        
        # 第一次调用 - 应该是缓存未命中
        result1 = await client.get_basic_info("000001")
        
        # 验证缓存未命中被记录
        cache_misses = metrics.cache_misses_total.get(cache_type="basic_info")
        assert cache_misses >= 1.0, "应该记录缓存未命中"
        
        # 如果第一次调用成功，第二次调用应该命中缓存
        if result1.get("ok"):
            result2 = await client.get_basic_info("000001")
            
            # 验证缓存命中被记录
            cache_hits = metrics.cache_hits_total.get(cache_type="basic_info")
            assert cache_hits >= 1.0, "应该记录缓存命中"
            
            # 验证缓存命中率
            hit_rate = metrics.get_cache_hit_rate("basic_info")
            assert 0.0 <= hit_rate <= 1.0, "缓存命中率应该在 0-1 之间"
    
    @pytest.mark.asyncio
    async def test_monitoring_summary(self):
        """测试监控摘要打印。"""
        # 重置指标
        akshare_metrics = get_akshare_metrics()
        agent_metrics = get_agent_metrics()
        akshare_metrics.reset()
        agent_metrics.reset()
        
        # 模拟一些指标
        akshare_metrics.record_api_call("test_api", 1.5, "success")
        akshare_metrics.record_cache_hit("basic_info")
        akshare_metrics.record_cache_miss("basic_info")
        agent_metrics.record_execution("TestAgent", 2.5, "success")
        
        # 打印摘要（不应该抛出异常）
        try:
            print_monitoring_summary()
            assert True, "监控摘要打印成功"
        except Exception as e:
            pytest.fail(f"监控摘要打印失败: {e}")
    
    @pytest.mark.asyncio
    async def test_multiple_cache_types(self):
        """测试多种缓存类型的监控。"""
        # 重置指标
        metrics = get_akshare_metrics()
        metrics.reset()
        
        # 创建客户端
        client = AkShareClient(enable_cache=True, cache_ttl=60)
        
        # 调用不同的方法
        await client.get_basic_info("000001")
        await client.get_achievement("000001")
        await client.get_analysis("000001")
        
        # 验证不同缓存类型都被记录
        basic_info_misses = metrics.cache_misses_total.get(cache_type="basic_info")
        achievement_misses = metrics.cache_misses_total.get(cache_type="achievement")
        analysis_misses = metrics.cache_misses_total.get(cache_type="analysis")
        
        # 至少应该有一些缓存未命中（第一次调用）
        total_misses = basic_info_misses + achievement_misses + analysis_misses
        assert total_misses >= 1.0, "应该记录多种缓存类型的未命中"
