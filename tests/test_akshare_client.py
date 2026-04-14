"""
AkShareClient 完整单元测试。

测试范围：
1. 基础功能（初始化、限流、重试）
2. 成功获取数据场景
3. 重试机制
4. 限流机制
5. 缓存机制
6. 并发获取
7. 异常处理
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

# 确保 backend 在 path 上
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from pkg.akshare_client import AkShareClient


class TestAkShareClientInit:
    """测试 AkShareClient 初始化。"""
    
    def test_init_with_custom_params(self):
        """测试自定义参数初始化。"""
        client = AkShareClient(
            max_retries=5,
            retry_delay=2.0,
            request_interval=1.0,
            cache_ttl=600,
            enable_cache=False,
        )
        
        assert client.max_retries == 5
        assert client.retry_delay == 2.0
        assert client.request_interval == 1.0
        assert client.cache_ttl == 600
        assert client.enable_cache is False
        assert client._last_request_time == 0
        assert client.logger is not None
        assert client._cache == {}
        assert client._cache_hits == 0
        assert client._cache_misses == 0
    
    def test_init_with_default_params(self):
        """测试默认参数初始化。"""
        client = AkShareClient()
        
        assert client.max_retries == 3
        assert client.retry_delay == 1.0
        assert client.request_interval == 0.5
        assert client.cache_ttl == 300
        assert client.enable_cache is True


class TestRateLimiting:
    """测试限流机制。"""
    
    @pytest.mark.asyncio
    async def test_rate_limit_first_call(self):
        """测试限流：第一次调用不需要等待。"""
        client = AkShareClient(request_interval=0.5)
        
        start = time.time()
        await client._rate_limit()
        elapsed = time.time() - start
        
        # 第一次调用应该立即返回
        assert elapsed < 0.1
        assert client._last_request_time > 0
    
    @pytest.mark.asyncio
    async def test_rate_limit_second_call(self):
        """测试限流：第二次调用需要等待。"""
        client = AkShareClient(request_interval=0.3)
        
        # 第一次调用
        await client._rate_limit()
        
        # 立即第二次调用
        start = time.time()
        await client._rate_limit()
        elapsed = time.time() - start
        
        # 应该等待约 0.3 秒
        assert 0.25 < elapsed < 0.4
    
    @pytest.mark.asyncio
    async def test_rate_limit_no_wait_after_interval(self):
        """测试间隔时间后不需要等待。"""
        client = AkShareClient(request_interval=0.2)
        
        # 第一次调用
        await client._rate_limit()
        
        # 等待超过间隔时间
        await asyncio.sleep(0.3)
        
        # 第二次调用应该不需要等待
        start = time.time()
        await client._rate_limit()
        elapsed = time.time() - start
        
        assert elapsed < 0.1


class TestRetryMechanism:
    """测试重试机制。"""
    
    @pytest.mark.asyncio
    async def test_retry_call_success_first_try(self):
        """测试第一次调用成功。"""
        client = AkShareClient()
        
        # 模拟成功的 AkShare 调用
        mock_func = MagicMock()
        mock_df = pd.DataFrame([
            {"item": "基金代码", "value": "000001"},
            {"item": "基金名称", "value": "华夏成长"},
        ])
        mock_func.return_value = mock_df
        mock_func.__name__ = "test_func"
        
        result = await client._retry_call(mock_func, symbol="000001")
        
        assert result["ok"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["item"] == "基金代码"
        assert mock_func.call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_call_retry_then_success(self):
        """测试第一次失败，第二次成功。"""
        client = AkShareClient(max_retries=3, retry_delay=0.1, request_interval=0.1)
        
        # 模拟第一次失败，第二次成功
        mock_func = MagicMock()
        mock_df = pd.DataFrame([{"item": "基金代码", "value": "000001"}])
        mock_func.side_effect = [
            Exception("Network error"),
            mock_df,
        ]
        mock_func.__name__ = "test_func"
        
        start = time.time()
        result = await client._retry_call(mock_func, symbol="000001")
        elapsed = time.time() - start
        
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert mock_func.call_count == 2
        # 应该等待了约 0.1 秒（第一次重试延迟）+ 限流开销
        assert 0.1 < elapsed < 0.6
    
    @pytest.mark.asyncio
    async def test_retry_call_all_failed(self):
        """测试所有重试都失败。"""
        client = AkShareClient(max_retries=3, retry_delay=0.05, request_interval=0.1)
        
        # 模拟所有调用都失败
        mock_func = MagicMock()
        mock_func.side_effect = Exception("Network error")
        mock_func.__name__ = "test_func"
        
        start = time.time()
        result = await client._retry_call(mock_func, symbol="000001")
        elapsed = time.time() - start
        
        assert result["ok"] is False
        assert "Network error" in result["message"]
        assert mock_func.call_count == 3
        # 应该等待了 0.05 + 0.1 + 0.2 = 0.35 秒（指数退避）+ 限流开销
        assert elapsed > 0.1  # 至少有一些延迟
    
    @pytest.mark.asyncio
    async def test_retry_call_exponential_backoff(self):
        """测试指数退避策略。"""
        client = AkShareClient(max_retries=3, retry_delay=0.1, request_interval=0.1)
        
        mock_func = MagicMock()
        mock_func.side_effect = Exception("Network error")
        mock_func.__name__ = "test_func"
        
        start = time.time()
        await client._retry_call(mock_func)
        elapsed = time.time() - start
        
        # 指数退避：0.1 + 0.2 + 0.4 = 0.7 秒
        # 加上限流和其他开销
        assert elapsed > 0.2  # 至少有一些延迟
        assert mock_func.call_count == 3

class TestDataRetrieval:
    """测试数据获取功能。"""
    
    @pytest.mark.asyncio
    async def test_get_basic_info_success(self):
        """测试成功获取基本信息。"""
        client = AkShareClient()
        
        # Mock AkShare API
        mock_df = pd.DataFrame([
            {"item": "基金代码", "value": "000001"},
            {"item": "基金名称", "value": "华夏成长"},
            {"item": "基金类型", "value": "混合型"},
        ])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", return_value=mock_df):
            result = await client.get_basic_info("000001")
            
            assert result["ok"] is True
            assert len(result["data"]) == 3
            assert result["data"][0]["item"] == "基金代码"
            assert result["data"][0]["value"] == "000001"
    
    @pytest.mark.asyncio
    async def test_get_achievement_success(self):
        """测试成功获取业绩表现。"""
        client = AkShareClient()
        
        # Mock AkShare API
        mock_df = pd.DataFrame([
            {"item": "近1月", "value": "5.20%"},
            {"item": "近3月", "value": "12.50%"},
            {"item": "近1年", "value": "25.60%"},
        ])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", return_value=mock_df):
            result = await client.get_achievement("000001")
            
            assert result["ok"] is True
            assert len(result["data"]) == 3
            assert result["data"][0]["item"] == "近1月"
    
    @pytest.mark.asyncio
    async def test_get_nav_data_success(self):
        """测试成功获取净值数据。"""
        client = AkShareClient()
        
        # Mock AkShare API
        mock_df = pd.DataFrame([
            {"净值日期": "2024-01-01", "单位净值": 1.0000},
            {"净值日期": "2024-01-02", "单位净值": 1.0100},
            {"净值日期": "2024-01-03", "单位净值": 1.0200},
        ])
        
        with patch("pkg.akshare_client.ak.fund_open_fund_info_em", return_value=mock_df):
            result = await client.get_nav_data("000001", period="1年")
            
            assert result["ok"] is True
            assert len(result["data"]) == 3
            assert result["data"][0]["净值日期"] == "2024-01-01"
    
    @pytest.mark.asyncio
    async def test_get_detail_hold_success(self):
        """测试成功获取资产配置。"""
        client = AkShareClient()
        
        # Mock AkShare API
        mock_df = pd.DataFrame([
            {"资产类型": "股票", "仓位占比": "65.50%"},
            {"资产类型": "债券", "仓位占比": "25.30%"},
            {"资产类型": "现金", "仓位占比": "9.20%"},
        ])
        
        with patch("pkg.akshare_client.ak.fund_portfolio_hold_em", return_value=mock_df):
            result = await client.get_detail_hold("000001")
            
            assert result["ok"] is True
            assert len(result["data"]) == 3
            assert result["data"][0]["资产类型"] == "股票"
class TestConcurrentRetrieval:
    """测试并发获取功能。"""
    
    @pytest.mark.asyncio
    async def test_get_all_data_success(self):
        """测试成功并发获取所有数据。"""
        client = AkShareClient(request_interval=0.1)
        
        # Mock 所有 AkShare API
        mock_basic_df = pd.DataFrame([{"item": "基金代码", "value": "000001"}])
        mock_achievement_df = pd.DataFrame([{"item": "近1月", "value": "5.20%"}])
        mock_nav_df = pd.DataFrame([{"净值日期": "2024-01-01", "单位净值": 1.0000}])
        mock_hold_df = pd.DataFrame([{"资产类型": "股票", "仓位占比": "65.50%"}])
        mock_info_df = pd.DataFrame([{"item": "管理费率", "value": "1.50%"}])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", return_value=mock_basic_df), \
             patch("pkg.akshare_client.ak.fund_open_fund_info_em", return_value=mock_nav_df), \
             patch("pkg.akshare_client.ak.fund_portfolio_hold_em", return_value=mock_hold_df):
            
            result = await client.get_all_data("000001")
            
            assert "basic_info" in result
            assert "achievement" in result
            assert "analysis" in result
            assert "detail_hold" in result
            assert "detail_info" in result
            assert "nav_data" in result
            
            # 验证每个数据源都有结果
            assert result["basic_info"]["ok"] is True
            assert result["nav_data"]["ok"] is True
            assert result["detail_hold"]["ok"] is True
    
    @pytest.mark.asyncio
    async def test_get_all_data_partial_failure(self):
        """测试部分数据获取失败。"""
        client = AkShareClient(request_interval=0.1, max_retries=1)
        
        # Mock 部分成功，部分失败
        mock_basic_df = pd.DataFrame([{"item": "基金代码", "value": "000001"}])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", return_value=mock_basic_df), \
             patch("pkg.akshare_client.ak.fund_open_fund_info_em", side_effect=Exception("API Error")), \
             patch("pkg.akshare_client.ak.fund_portfolio_hold_em", return_value=mock_basic_df):
            
            result = await client.get_all_data("000001")
            
            # 成功的数据源
            assert result["basic_info"]["ok"] is True
            assert result["detail_hold"]["ok"] is True
            
            # 失败的数据源
            assert result["nav_data"]["ok"] is False
            assert "API Error" in result["nav_data"]["message"]
    
    @pytest.mark.asyncio
    async def test_get_all_data_concurrency_limit(self):
        """测试并发限制（最多3个并发）。"""
        client = AkShareClient(request_interval=0.1)
        
        call_times = []
        
        def mock_api(*args, **kwargs):
            call_times.append(time.time())
            time.sleep(0.2)  # 模拟API调用耗时
            return pd.DataFrame([{"item": "test", "value": "test"}])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", side_effect=mock_api), \
             patch("pkg.akshare_client.ak.fund_open_fund_info_em", side_effect=mock_api), \
             patch("pkg.akshare_client.ak.fund_portfolio_hold_em", side_effect=mock_api):
            
            start_time = time.time()
            result = await client.get_all_data("000001")
            total_time = time.time() - start_time
            
            # 6个API调用，最多3个并发，每个耗时0.2秒
            # 理论上需要 2 * 0.2 = 0.4 秒（加上一些开销）
            assert total_time < 1.0  # 应该明显少于串行执行的时间
            assert len(call_times) == 6  # 应该调用了6个API
class TestExceptionHandling:
    """测试异常处理。"""
    
    @pytest.mark.asyncio
    async def test_handle_network_error(self):
        """测试网络错误处理。"""
        client = AkShareClient(max_retries=2, retry_delay=0.1)
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", side_effect=ConnectionError("Network error")):
            result = await client.get_basic_info("000001")
            
            assert result["ok"] is False
            assert "Network error" in result["message"]
    
    @pytest.mark.asyncio
    async def test_handle_timeout_error(self):
        """测试超时错误处理。"""
        client = AkShareClient(max_retries=2, retry_delay=0.1)
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", side_effect=TimeoutError("Request timeout")):
            result = await client.get_basic_info("000001")
            
            assert result["ok"] is False
            assert "Request timeout" in result["message"]
    
    @pytest.mark.asyncio
    async def test_handle_empty_dataframe(self):
        """测试空 DataFrame 处理。"""
        client = AkShareClient()
        
        # Mock 返回空 DataFrame
        empty_df = pd.DataFrame()
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", return_value=empty_df):
            result = await client.get_basic_info("000001")
            
            assert result["ok"] is True
            assert result["data"] == []
    
    @pytest.mark.asyncio
    async def test_handle_invalid_symbol(self):
        """测试无效基金代码处理。"""
        client = AkShareClient(max_retries=1)
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", side_effect=ValueError("Invalid symbol")):
            result = await client.get_basic_info("INVALID")
            
            assert result["ok"] is False
            assert "Invalid symbol" in result["message"]
    
    @pytest.mark.asyncio
    async def test_handle_api_rate_limit_error(self):
        """测试 API 限流错误处理。"""
        client = AkShareClient(max_retries=2, retry_delay=0.1)
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", side_effect=Exception("Rate limit exceeded")):
            result = await client.get_basic_info("000001")
            
            assert result["ok"] is False
            assert "Rate limit exceeded" in result["message"]


class TestCacheIntegration:
    """测试缓存集成。"""
    
    @pytest.mark.asyncio
    async def test_cache_hit_on_second_call(self):
        """测试第二次调用命中缓存。"""
        client = AkShareClient(cache_ttl=300, request_interval=0.1)
        
        # Mock AkShare API
        mock_df = pd.DataFrame([{"基金代码": "000001", "基金名称": "测试基金"}])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", return_value=mock_df) as mock_api:
            # 第一次调用，应该调用 API
            result1 = await client.get_basic_info("000001")
            assert result1["ok"] is True
            assert mock_api.call_count == 1
            
            # 第二次调用，应该命中缓存（不会再调用 API）
            result2 = await client.get_basic_info("000001")
            assert result2["ok"] is True
            assert result2 == result1
            assert mock_api.call_count == 1  # 仍然是1次调用
    
    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """测试禁用缓存时每次都调用 API。"""
        client = AkShareClient(enable_cache=False, request_interval=0.1)
        
        call_count = 0
        
        def mock_api(symbol):
            nonlocal call_count
            call_count += 1
            return pd.DataFrame([{"基金代码": symbol, "call": call_count}])
        
        with patch("pkg.akshare_client.ak.fund_individual_basic_info_xq", side_effect=mock_api):
            # 多次调用同一个基金代码
            result1 = await client.get_basic_info("000001")
            result2 = await client.get_basic_info("000001")
            
            # 每次都应该调用 API
            assert result1["data"][0]["call"] == 1
            assert result2["data"][0]["call"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])