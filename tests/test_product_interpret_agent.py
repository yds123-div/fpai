"""
ProductInterpretAgent 单元测试。

测试 ProductInterpretAgent 的核心功能：
- 基金代码提取
- 数据完整性检查
- AkShare 数据集成
- 兜底机制
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.fund_agent.product_interpret.agent import ProductInterpretAgent
from agents.fund_agent.runtime import AgentRunContext


class TestProductInterpretAgent:
    """ProductInterpretAgent 测试类。"""
    
    def test_extract_symbol_success(self):
        """测试成功提取基金代码。"""
        agent = ProductInterpretAgent()
        
        # 测试各种格式
        assert agent._extract_symbol("分析基金 000001") == "000001"
        assert agent._extract_symbol("帮我看看 110022") == "110022"
        assert agent._extract_symbol("000001 这只基金怎么样") == "000001"
        assert agent._extract_symbol("基金代码：000001") == "000001"
    
    def test_extract_symbol_failure(self):
        """测试提取基金代码失败的情况。"""
        agent = ProductInterpretAgent()
        
        # 没有基金代码
        assert agent._extract_symbol("帮我看看华夏成长") is None
        assert agent._extract_symbol("基金分析") is None
        assert agent._extract_symbol("") is None
        assert agent._extract_symbol(None) is None
        
        # 格式不正确（不是 6 位数字）
        assert agent._extract_symbol("12345") is None  # 5 位
        assert agent._extract_symbol("1234567") is None  # 7 位
    
    def test_has_sufficient_data_success(self):
        """测试数据完整性检查 - 成功情况。"""
        agent = ProductInterpretAgent()
        
        # 完整数据
        fund_data = {
            "ok": True,
            "data": {
                "symbol": "000001",
                "basic_info": {"ok": True, "data": [{"item": "基金代码", "value": "000001"}]},
                "achievement": {"ok": True, "data": [{"item": "近1年", "value": "10.5%"}]},
            }
        }
        
        assert agent._has_sufficient_data(fund_data) is True
    
    def test_has_sufficient_data_failure(self):
        """测试数据完整性检查 - 失败情况。"""
        agent = ProductInterpretAgent()
        
        # 缺少基本信息
        fund_data_no_basic = {
            "ok": True,
            "data": {
                "basic_info": {"ok": False},
                "achievement": {"ok": True, "data": []},
            }
        }
        assert agent._has_sufficient_data(fund_data_no_basic) is False
        
        # 缺少业绩数据
        fund_data_no_achievement = {
            "ok": True,
            "data": {
                "basic_info": {"ok": True, "data": []},
                "achievement": {"ok": False},
            }
        }
        assert agent._has_sufficient_data(fund_data_no_achievement) is False
        
        # 顶层 ok 为 False
        fund_data_not_ok = {
            "ok": False,
            "message": "Failed to fetch data"
        }
        assert agent._has_sufficient_data(fund_data_not_ok) is False
        
        # 空数据
        assert agent._has_sufficient_data({}) is False
        assert agent._has_sufficient_data(None) is False
    
    @pytest.mark.asyncio
    async def test_run_with_akshare_data(self):
        """测试使用 AkShare 数据的完整流程。"""
        agent = ProductInterpretAgent()
        
        # Mock AkShareClient
        mock_fund_data = {
            "ok": True,
            "data": {
                "symbol": "000001",
                "basic_info": {"ok": True, "data": [{"item": "基金代码", "value": "000001"}]},
                "achievement": {"ok": True, "data": [{"item": "近1年", "value": "10.5%"}]},
                "analysis": {"ok": True, "data": []},
                "detail_hold": {"ok": True, "data": []},
                "detail_info": {"ok": True, "data": []},
                "nav_data": {"ok": True, "data": []},
            }
        }
        
        agent.akshare_client.get_all_data = AsyncMock(return_value=mock_fund_data)
        agent.akshare_client.get_nav_data = AsyncMock(return_value={"ok": False})
        agent.akshare_client.get_industry_allocation = AsyncMock(return_value={"ok": False})
        agent.akshare_client.get_portfolio_hold = AsyncMock(return_value={"ok": False})
        
        # Mock LLM call
        with patch('agents.fund_agent.runtime._llm_call_maybe_stream', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "【基本信息】\n这是一只测试基金。"
            
            # Mock context
            ctx = MagicMock(spec=AgentRunContext)
            ctx.trace_id = "test-trace-123"
            ctx.answer_id = "test-answer-456"
            ctx.show_thinking = False
            
            # 执行
            result = await agent.run("分析基金 000001", ctx)
            
            # 验证
            assert result is not None
            assert isinstance(result, str)
            
            # 验证调用了 AkShareClient
            agent.akshare_client.get_all_data.assert_called_once_with("000001")
    
    @pytest.mark.asyncio
    async def test_run_fallback_to_skill(self):
        """测试回退到 skill 逻辑。"""
        agent = ProductInterpretAgent()
        
        # Mock AkShareClient 返回数据不足
        mock_fund_data = {
            "ok": True,
            "data": {
                "basic_info": {"ok": False},
                "achievement": {"ok": False},
            }
        }
        
        agent.akshare_client.get_all_data = AsyncMock(return_value=mock_fund_data)
        
        # Mock skill call
        with patch('agents.fund_agent.runtime.run_configured_skills', new_callable=AsyncMock) as mock_skill:
            mock_skill.return_value = None
            
            # Mock LLM call
            with patch('agents.fund_agent.runtime._llm_call_maybe_stream', new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = "【产品解析】数据不足。"
                
                # Mock context
                ctx = MagicMock(spec=AgentRunContext)
                ctx.trace_id = "test-trace-123"
                ctx.answer_id = "test-answer-456"
                ctx.show_thinking = False
                ctx.permission_context = {}
                
                # 执行
                result = await agent.run("分析基金 000001", ctx)
                
                # 验证
                assert result is not None
                assert isinstance(result, str)
                
                # 验证调用了 skill
                mock_skill.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_no_symbol(self):
        """测试没有基金代码的情况。"""
        agent = ProductInterpretAgent()
        
        # Mock skill call
        with patch('agents.fund_agent.runtime.run_configured_skills', new_callable=AsyncMock) as mock_skill:
            mock_skill.return_value = None
            
            # Mock LLM call
            with patch('agents.fund_agent.runtime._llm_call_maybe_stream', new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = "请提供基金代码。"
                
                # Mock context
                ctx = MagicMock(spec=AgentRunContext)
                ctx.trace_id = "test-trace-123"
                ctx.answer_id = "test-answer-456"
                ctx.show_thinking = False
                ctx.permission_context = {}
                
                # 执行（没有基金代码）
                result = await agent.run("帮我分析一下基金", ctx)
                
                # 验证
                assert result is not None
                
                # 验证没有调用 AkShareClient（因为没有提取到基金代码）
                # 直接回退到 skill 逻辑
                mock_skill.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

