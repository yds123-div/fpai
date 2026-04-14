"""
AkShareClient 基础功能测试。

测试 AkShareClient 的初始化、限流、重试等基础功能。
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


class TestAkShareClientBasic:
    """AkShareClient 基础功能测试类。"""
    
    def test_init(self):
        """测试 AkShareClient 初始化。"""
        client = AkShareClient(
            max_retries=5,
            retry_delay=2.0,
            request_interval=1.0,
        )
        
        assert client.max_retries == 5
        assert client.retry_delay == 2.0
        assert client.request_interval == 1.0
        assert client._last_request_time == 0
        assert client.logger is not None
    
    def test_init_default_values(self):
        """测试 AkShareClient 默认参数初始化。"""
        client = AkShareClient()
        
        assert client.max_retries == 3
        assert client.retry_delay == 1.0
        assert client.request_interval == 0.5
    
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
    async def test_retry_call_success(self):
        """测试重试机制：第一次调用成功。"""
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
        """测试重试机制：第一次失败，第二次成功。"""
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
        """测试重试机制：所有重试都失败。"""
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
        """测试重试机制：验证指数退避策略。"""
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
    
    @pytest.mark.asyncio
    async def test_retry_call_non_dataframe_result(self):
        """测试重试机制：处理非 DataFrame 返回值。"""
        client = AkShareClient()
        
        mock_func = MagicMock()
        mock_func.return_value = {"key": "value"}
        mock_func.__name__ = "test_func"
        
        result = await client._retry_call(mock_func)
        
        assert result["ok"] is True
        assert result["data"] == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
