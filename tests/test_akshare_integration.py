"""
AkShareClient 集成测试。

演示如何使用 AkShareClient 的 6 个核心方法获取完整的基金数据。
这个测试文件可以作为使用示例。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# 确保 backend 在 path 上
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from pkg.akshare_client import AkShareClient


class TestAkShareIntegration:
    """AkShareClient 集成测试类。"""
    
    @pytest.mark.asyncio
    async def test_get_complete_fund_data(self):
        """测试获取单只基金的完整数据。
        
        这个测试演示了如何使用 6 个核心方法获取一只基金的所有数据。
        """
        client = AkShareClient(request_interval=0.1)
        symbol = "000001"
        
        # 模拟各种数据
        mock_basic_info = pd.DataFrame([
            {"item": "基金代码", "value": "000001"},
            {"item": "基金名称", "value": "华夏成长"},
            {"item": "基金类型", "value": "混合型"},
        ])
        
        mock_achievement = pd.DataFrame([
            {"时间段": "近1月", "收益率": "5.2%"},
            {"时间段": "近1年", "收益率": "35.8%"},
        ])
        
        mock_analysis = pd.DataFrame([
            {"指标": "波动率", "值": "15.2%"},
            {"指标": "夏普比率", "值": "1.8"},
        ])
        
        mock_detail_hold = pd.DataFrame([
            {"资产类型": "股票", "仓位占比": 65.5},
            {"资产类型": "债券", "仓位占比": 25.3},
        ])
        
        mock_detail_info = pd.DataFrame([
            {"费用类型": "管理费率", "费率": "1.5%"},
            {"费用类型": "托管费率", "费率": "0.25%"},
        ])
        
        mock_nav_data = pd.DataFrame([
            {"净值日期": "2024-01-01", "单位净值": 1.5000},
            {"净值日期": "2024-01-02", "单位净值": 1.5100},
        ])
        
        # 1. 获取基本信息
        with patch("akshare.fund_individual_basic_info_xq", return_value=mock_basic_info):
            basic_info = await client.get_basic_info(symbol)
        
        assert basic_info["ok"] is True
        assert len(basic_info["data"]) == 3
        print(f"✓ 基本信息: {len(basic_info['data'])} 条记录")
        
        # 2. 获取业绩表现
        with patch("akshare.fund_individual_achievement_xq", return_value=mock_achievement):
            achievement = await client.get_achievement(symbol)
        
        assert achievement["ok"] is True
        assert len(achievement["data"]) == 2
        print(f"✓ 业绩表现: {len(achievement['data'])} 条记录")
        
        # 3. 获取风险指标
        with patch("akshare.fund_individual_analysis_xq", return_value=mock_analysis):
            analysis = await client.get_analysis(symbol)
        
        assert analysis["ok"] is True
        assert len(analysis["data"]) == 2
        print(f"✓ 风险指标: {len(analysis['data'])} 条记录")
        
        # 4. 获取资产配置
        with patch("akshare.fund_individual_detail_hold_xq", return_value=mock_detail_hold):
            detail_hold = await client.get_detail_hold(symbol)
        
        assert detail_hold["ok"] is True
        assert len(detail_hold["data"]) == 2
        print(f"✓ 资产配置: {len(detail_hold['data'])} 条记录")
        
        # 5. 获取费率信息
        with patch("akshare.fund_individual_detail_info_xq", return_value=mock_detail_info):
            detail_info = await client.get_detail_info(symbol)
        
        assert detail_info["ok"] is True
        assert len(detail_info["data"]) == 2
        print(f"✓ 费率信息: {len(detail_info['data'])} 条记录")
        
        # 6. 获取净值走势
        with patch("akshare.fund_open_fund_info_em", return_value=mock_nav_data):
            nav_data = await client.get_nav_data(symbol, period="1年")
        
        assert nav_data["ok"] is True
        assert len(nav_data["data"]) == 2
        print(f"✓ 净值走势: {len(nav_data['data'])} 条记录")
        
        # 汇总结果
        fund_data = {
            "symbol": symbol,
            "basic_info": basic_info,
            "achievement": achievement,
            "analysis": analysis,
            "detail_hold": detail_hold,
            "detail_info": detail_info,
            "nav_data": nav_data,
        }
        
        # 验证所有数据都成功获取
        assert all(
            data["ok"] is True
            for key, data in fund_data.items()
            if key != "symbol"
        )
        
        print(f"\n✓ 成功获取基金 {symbol} 的所有数据")
        print(f"  - 基本信息: {len(basic_info['data'])} 条")
        print(f"  - 业绩表现: {len(achievement['data'])} 条")
        print(f"  - 风险指标: {len(analysis['data'])} 条")
        print(f"  - 资产配置: {len(detail_hold['data'])} 条")
        print(f"  - 费率信息: {len(detail_info['data'])} 条")
        print(f"  - 净值走势: {len(nav_data['data'])} 条")
    
    @pytest.mark.asyncio
    async def test_handle_partial_data_failure(self):
        """测试部分数据获取失败的场景。
        
        在实际使用中，某些数据可能获取失败，系统应该能够优雅处理。
        """
        client = AkShareClient(max_retries=2, retry_delay=0.05, request_interval=0.1)
        symbol = "000001"
        
        mock_basic_info = pd.DataFrame([{"item": "基金代码", "value": "000001"}])
        
        # 1. 基本信息成功
        with patch("akshare.fund_individual_basic_info_xq", return_value=mock_basic_info):
            basic_info = await client.get_basic_info(symbol)
        
        assert basic_info["ok"] is True
        
        # 2. 业绩表现失败
        with patch(
            "akshare.fund_individual_achievement_xq",
            side_effect=Exception("API error"),
        ):
            achievement = await client.get_achievement(symbol)
        
        assert achievement["ok"] is False
        
        # 3. 风险指标成功
        mock_analysis = pd.DataFrame([{"指标": "波动率", "值": "15.2%"}])
        with patch("akshare.fund_individual_analysis_xq", return_value=mock_analysis):
            analysis = await client.get_analysis(symbol)
        
        assert analysis["ok"] is True
        
        # 验证：即使部分数据失败，其他数据仍然可用
        assert basic_info["ok"] is True
        assert achievement["ok"] is False
        assert analysis["ok"] is True
        
        print("\n✓ 部分数据失败场景处理正确")
        print(f"  - 基本信息: {'成功' if basic_info['ok'] else '失败'}")
        print(f"  - 业绩表现: {'成功' if achievement['ok'] else '失败'}")
        print(f"  - 风险指标: {'成功' if analysis['ok'] else '失败'}")
    
    @pytest.mark.asyncio
    async def test_different_nav_periods(self):
        """测试获取不同周期的净值数据。"""
        client = AkShareClient(request_interval=0.1)
        symbol = "000001"
        
        mock_nav_data = pd.DataFrame([
            {"净值日期": "2024-01-01", "单位净值": 1.5000},
        ])
        
        periods = ["1月", "3月", "6月", "1年", "3年"]
        results = {}
        
        for period in periods:
            with patch("akshare.fund_open_fund_info_em", return_value=mock_nav_data):
                result = await client.get_nav_data(symbol, period=period)
            
            results[period] = result
            assert result["ok"] is True
        
        print(f"\n✓ 成功获取 {len(periods)} 个不同周期的净值数据")
        for period in periods:
            print(f"  - {period}: {len(results[period]['data'])} 条记录")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

