"""
测试 ProductCompareAgent 的 AkShare 数据集成。

测试场景：
1. 成功获取多只基金数据并生成对比分析
2. 部分基金数据获取失败的降级处理
3. 数据不足时回退到 skill 逻辑
4. 提取基金代码列表
5. 并发获取多只基金数据
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agents.fund_agent.product_compare.agent import ProductCompareAgent
from agents.fund_agent.runtime import AgentRunContext


@pytest.fixture
def agent():
    """创建 ProductCompareAgent 实例。"""
    return ProductCompareAgent()


@pytest.fixture
def mock_ctx():
    """创建模拟的运行上下文。"""
    ctx = MagicMock(spec=AgentRunContext)
    ctx.trace_id = "test-trace-id"
    ctx.answer_id = "test-answer-id"
    ctx.session_id = "test-session-id"
    ctx.show_thinking = False
    ctx.permission_context = {}
    return ctx


@pytest.fixture
def mock_fund_data():
    """创建模拟的基金数据。"""
    return {
        "ok": True,
        "symbol": "000001",
        "data": {
            "basic_info": {
                "ok": True,
                "data": [
                    {"item": "基金名称", "value": "华夏成长"},
                    {"item": "基金代码", "value": "000001"},
                    {"item": "基金类型", "value": "混合型"},
                ],
            },
            "achievement": {
                "ok": True,
                "data": [
                    {"period": "近1年", "return": "15.23%"},
                    {"period": "近3年", "return": "45.67%"},
                ],
            },
            "asset_allocation": {
                "ok": True,
                "data": {
                    "top_holdings": [
                        {"股票名称": "贵州茅台", "股票代码": "600519", "占净值比例": "5.23%"},
                    ],
                },
            },
        },
    }


class TestProductCompareAgent:
    """测试 ProductCompareAgent。"""

    def test_extract_symbols(self, agent):
        """测试提取基金代码列表。"""
        # 测试正常提取
        symbols = agent._extract_symbols("对比 000001 和 110011")
        assert symbols == ["000001", "110011"]
        
        # 测试多个代码
        symbols = agent._extract_symbols("分析 000001、110011、161039 这三只基金")
        assert symbols == ["000001", "110011", "161039"]
        
        # 测试去重
        symbols = agent._extract_symbols("对比 000001 和 000001")
        assert symbols == ["000001"]
        
        # 测试最多 5 个
        symbols = agent._extract_symbols("000001 110011 161039 163402 519674 000011")
        assert len(symbols) == 5
        assert symbols == ["000001", "110011", "161039", "163402", "519674"]
        
        # 测试空输入
        symbols = agent._extract_symbols("")
        assert symbols == []
        
        # 测试无代码
        symbols = agent._extract_symbols("帮我分析基金")
        assert symbols == []

    def test_has_sufficient_data(self, agent, mock_fund_data):
        """测试数据完整性检查。"""
        # 测试完整数据
        assert agent._has_sufficient_data(mock_fund_data) is True
        
        # 测试缺少基本信息
        incomplete_data = {
            "ok": True,
            "data": {
                "basic_info": {"ok": False},
                "achievement": {"ok": True, "data": []},
            },
        }
        assert agent._has_sufficient_data(incomplete_data) is False
        
        # 测试缺少业绩数据
        incomplete_data = {
            "ok": True,
            "data": {
                "basic_info": {"ok": True, "data": []},
                "achievement": {"ok": False},
            },
        }
        assert agent._has_sufficient_data(incomplete_data) is False
        
        # 测试 ok=False
        assert agent._has_sufficient_data({"ok": False}) is False
        
        # 测试空数据
        assert agent._has_sufficient_data({}) is False

    @pytest.mark.asyncio
    async def test_fetch_multiple_funds_success(self, agent, mock_fund_data):
        """测试并发获取多只基金数据（成功场景）。"""
        # Mock AkShareClient.get_all_data
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                {"ok": True, "data": mock_fund_data["data"]},
                {"ok": True, "data": mock_fund_data["data"]},
            ]
            
            funds_data = await agent._fetch_multiple_funds(["000001", "110011"])
            
            assert len(funds_data) == 2
            assert funds_data[0]["symbol"] == "000001"
            assert funds_data[0]["ok"] is True
            assert funds_data[1]["symbol"] == "110011"
            assert funds_data[1]["ok"] is True

    @pytest.mark.asyncio
    async def test_fetch_multiple_funds_partial_failure(self, agent, mock_fund_data):
        """测试并发获取多只基金数据（部分失败场景）。"""
        # Mock AkShareClient.get_all_data
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                {"ok": True, "data": mock_fund_data["data"]},
                Exception("Network error"),
            ]
            
            funds_data = await agent._fetch_multiple_funds(["000001", "110011"])
            
            assert len(funds_data) == 2
            assert funds_data[0]["ok"] is True
            assert funds_data[1]["ok"] is False
            assert "error" in funds_data[1]

    @pytest.mark.asyncio
    async def test_generate_comparison_text(self, agent, mock_ctx, mock_fund_data):
        """测试生成对比分析文本。"""
        funds_data = [
            {"symbol": "000001", "data": mock_fund_data["data"]},
            {"symbol": "110011", "data": mock_fund_data["data"]},
        ]
        
        # Mock _llm_call_maybe_stream
        with patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "【基本信息】\n华夏成长（000001）..."
            
            llm_text = await agent._generate_comparison_text(
                funds_data,
                "对比 000001 和 110011",
                "system prompt",
                mock_ctx,
            )
            
            assert "华夏成长" in llm_text
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_akshare_data(self, agent, mock_ctx, mock_fund_data):
        """测试使用 AkShare 数据的完整流程。"""
        question = "对比 000001 和 110011"
        
        # Mock 各个依赖
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_compare.agent.build_compare_output") as mock_build:
            
            mock_get.return_value = {"ok": True, "data": mock_fund_data["data"]}
            mock_llm.return_value = "【基本信息】\n华夏成长（000001）..."
            mock_build.return_value = {
                "type": "fund_compare",
                "text": "【基本信息】\n华夏成长（000001）...",
            }
            
            result = await agent.run(question, mock_ctx)
            
            # 验证返回 JSON 字符串
            assert isinstance(result, str)
            import json
            output = json.loads(result)
            assert output["type"] == "fund_compare"

    @pytest.mark.asyncio
    async def test_run_fallback_to_skill(self, agent, mock_ctx):
        """测试回退到 skill 逻辑。"""
        question = "对比基金"  # 没有基金代码
        
        # Mock skill 逻辑
        with patch("agents.fund_agent.product_compare.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_compare.agent.build_compare_output") as mock_build:
            
            mock_skill.return_value = {"payload": {"ok": True, "funds": []}}
            mock_llm.return_value = "【产品对比】..."
            mock_build.return_value = {"type": "fund_compare", "text": "【产品对比】..."}
            
            result = await agent.run(question, mock_ctx)
            
            # 验证调用了 skill
            mock_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_insufficient_valid_funds(self, agent, mock_ctx):
        """测试有效基金数量不足时回退到 skill。"""
        question = "对比 000001 和 110011"
        
        # Mock 只有 1 只基金数据有效
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_compare.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm:
            
            mock_get.side_effect = [
                {"ok": True, "data": {"basic_info": {"ok": True}, "achievement": {"ok": True}}},
                {"ok": False, "error": "Data not available"},
            ]
            mock_skill.return_value = {"payload": {"ok": True, "funds": []}}
            mock_llm.return_value = "【产品对比】..."
            
            result = await agent.run(question, mock_ctx)
            
            # 验证回退到 skill
            mock_skill.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
