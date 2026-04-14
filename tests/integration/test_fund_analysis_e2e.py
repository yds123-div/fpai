"""
基金分析端到端集成测试。

测试场景：
1. 单基金解读端到端流程
2. 多基金对比端到端流程
3. 数据获取失败场景
4. 数据不足场景
5. 兜底机制
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from agents.fund_agent.product_interpret.agent import ProductInterpretAgent
from agents.fund_agent.product_compare.agent import ProductCompareAgent
from agents.fund_agent.runtime import AgentRunContext


@pytest.fixture
def mock_ctx():
    """创建模拟的运行上下文。"""
    ctx = MagicMock(spec=AgentRunContext)
    ctx.trace_id = "e2e-trace-id"
    ctx.answer_id = "e2e-answer-id"
    ctx.session_id = "e2e-session-id"
    ctx.show_thinking = False
    ctx.permission_context = {}
    return ctx


@pytest.fixture
def complete_fund_data():
    """创建完整的基金数据（模拟 AkShare 返回）。"""
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
                    {"item": "成立日期", "value": "2001-12-18"},
                    {"item": "基金规模", "value": "50.23亿元"},
                    {"item": "基金经理", "value": "张三"},
                    {"item": "管理费率", "value": "1.50%"},
                    {"item": "托管费率", "value": "0.25%"},
                ],
            },
            "achievement": {
                "ok": True,
                "data": [
                    {"period": "近1月", "return": "2.34%", "rank": "25/100"},
                    {"period": "近3月", "return": "5.67%", "rank": "30/100"},
                    {"period": "近6月", "return": "10.23%", "rank": "20/100"},
                    {"period": "近1年", "return": "15.23%", "rank": "15/100"},
                    {"period": "近3年", "return": "45.67%", "rank": "10/100"},
                ],
            },
            "profit_probability": {
                "ok": True,
                "data": [
                    {"period": "持有1月", "profit_prob": "65%", "avg_return": "2.1%"},
                    {"period": "持有3月", "profit_prob": "72%", "avg_return": "5.3%"},
                    {"period": "持有1年", "profit_prob": "85%", "avg_return": "14.8%"},
                ],
            },
            "asset_allocation": {
                "ok": True,
                "data": {
                    "report_date": "2024-12-31",
                    "asset_distribution": [
                        {"asset_type": "股票", "ratio": "65.23%"},
                        {"asset_type": "债券", "ratio": "20.45%"},
                        {"asset_type": "现金", "ratio": "14.32%"},
                    ],
                    "top_holdings": [
                        {"股票名称": "贵州茅台", "股票代码": "600519", "占净值比例": "5.23%"},
                        {"股票名称": "五粮液", "股票代码": "000858", "占净值比例": "4.12%"},
                        {"股票名称": "宁德时代", "股票代码": "300750", "占净值比例": "3.89%"},
                    ],
                },
            },
        },
    }


@pytest.fixture
def incomplete_fund_data():
    """创建不完整的基金数据（缺少业绩数据）。"""
    return {
        "ok": True,
        "symbol": "000002",
        "data": {
            "basic_info": {
                "ok": True,
                "data": [
                    {"item": "基金名称", "value": "测试基金"},
                    {"item": "基金代码", "value": "000002"},
                ],
            },
            "achievement": {
                "ok": False,
                "message": "数据不可用",
            },
        },
    }


class TestProductInterpretE2E:
    """测试 ProductInterpretAgent 端到端流程。"""

    @pytest.mark.asyncio
    async def test_single_fund_analysis_success(self, mock_ctx, complete_fund_data):
        """测试单基金解读成功场景（端到端）。"""
        agent = ProductInterpretAgent()
        question = "分析基金 000001"
        
        # Mock AkShareClient 和 LLM
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_interpret.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_interpret.agent._emit_progress", new_callable=AsyncMock):
            
            mock_get.return_value = complete_fund_data
            mock_llm.return_value = """【基本信息】
华夏成长（000001）是一只混合型基金，成立于2001年12月18日，由张三管理。基金规模为50.23亿元，管理费率1.50%，托管费率0.25%。数据截至2024年12月31日，时效性良好。

【业绩表现】
近1年收益率15.23%，在同类基金中排名15/100，表现优秀。近3年累计收益45.67%，排名10/100，长期业绩稳定。持有1年盈利概率85%，平均收益14.8%。

【资产配置】
股票资产占比65.23%，债券20.45%，现金14.32%。前三大重仓股为贵州茅台（5.23%）、五粮液（4.12%）、宁德时代（3.89%），持仓较为分散。

【分析结论】
华夏成长是一只业绩优秀的混合型基金，适合风险承受能力中等偏上的投资者长期持有。建议采用定投方式分批建仓。

【风险提示】
基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议，不代表财富管理专家的态度和观点。"""
            
            result = await agent.run(question, mock_ctx)
            
            # 验证返回结果
            assert isinstance(result, str)
            output = json.loads(result)
            
            # 验证结构化输出
            assert output["type"] == "fund_analysis"
            assert "text" in output
            assert "华夏成长" in output["text"]
            assert "000001" in output["text"]
            
            # 验证调用了 AkShare
            mock_get.assert_called_once_with("000001")
            
            # 验证调用了 LLM
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_fund_analysis_data_fetch_failure(self, mock_ctx):
        """测试数据获取失败场景。"""
        agent = ProductInterpretAgent()
        question = "分析基金 000001"
        
        # Mock AkShareClient 抛出异常
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_interpret.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_interpret.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_interpret.agent._emit_progress", new_callable=AsyncMock):
            
            mock_get.side_effect = Exception("Network error")
            mock_skill.return_value = None
            mock_llm.return_value = "【产品解析】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。"
            
            result = await agent.run(question, mock_ctx)
            
            # 验证回退到 skill 逻辑
            mock_skill.assert_called_once()
            
            # 验证返回兜底信息
            assert "未获取到" in result or "暂无法" in result

    @pytest.mark.asyncio
    async def test_single_fund_analysis_insufficient_data(self, mock_ctx, incomplete_fund_data):
        """测试数据不足场景。"""
        agent = ProductInterpretAgent()
        question = "分析基金 000002"
        
        # Mock AkShareClient 返回不完整数据
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_interpret.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_interpret.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_interpret.agent._emit_progress", new_callable=AsyncMock):
            
            mock_get.return_value = incomplete_fund_data
            mock_skill.return_value = None
            mock_llm.return_value = "【产品解析】数据不足，无法生成完整分析。"
            
            result = await agent.run(question, mock_ctx)
            
            # 验证回退到 skill 逻辑
            mock_skill.assert_called_once()


class TestProductCompareE2E:
    """测试 ProductCompareAgent 端到端流程。"""

    @pytest.mark.asyncio
    async def test_multi_fund_comparison_success(self, mock_ctx, complete_fund_data):
        """测试多基金对比成功场景（端到端）。"""
        agent = ProductCompareAgent()
        question = "对比 000001 和 110011"
        
        # 创建第二只基金数据
        fund2_data = {
            "ok": True,
            "symbol": "110011",
            "data": {
                "basic_info": {
                    "ok": True,
                    "data": [
                        {"item": "基金名称", "value": "易方达中小盘"},
                        {"item": "基金代码", "value": "110011"},
                        {"item": "基金类型", "value": "混合型"},
                    ],
                },
                "achievement": {
                    "ok": True,
                    "data": [
                        {"period": "近1年", "return": "18.45%"},
                        {"period": "近3年", "return": "52.34%"},
                    ],
                },
            },
        }
        
        # Mock AkShareClient 和 LLM
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_compare.agent._emit_progress", new_callable=AsyncMock):
            
            mock_get.side_effect = [complete_fund_data, fund2_data]
            mock_llm.return_value = """【基本信息】
华夏成长（000001）是混合型基金，规模50.23亿元。易方达中小盘（110011）也是混合型基金。两只基金类型相同，具有可比性。

【业绩表现】
华夏成长近1年收益15.23%，近3年收益45.67%。易方达中小盘近1年收益18.45%，近3年收益52.34%。易方达中小盘短期和长期业绩均优于华夏成长。

【分析结论】
综合对比，易方达中小盘业绩表现更优，适合追求较高收益的投资者。华夏成长规模更大，适合稳健型投资者。

【风险提示】
基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议，不代表财富管理专家的态度和观点。"""
            
            result = await agent.run(question, mock_ctx)
            
            # 验证返回结果
            assert isinstance(result, str)
            output = json.loads(result)
            
            # 验证结构化输出
            assert output["type"] == "fund_analysis"
            assert output.get("mode") == "compare"
            assert "sections" in output or "summary" in output
            # 验证包含两只基金的信息
            result_str = json.dumps(output, ensure_ascii=False)
            assert "华夏成长" in result_str or "000001" in result_str
            assert "易方达中小盘" in result_str or "110011" in result_str
            
            # 验证调用了 AkShare（2 次）
            assert mock_get.call_count == 2
            
            # 验证调用了 LLM
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_fund_comparison_partial_failure(self, mock_ctx, complete_fund_data):
        """测试部分基金数据获取失败场景。"""
        agent = ProductCompareAgent()
        question = "对比 000001 和 110011"
        
        # Mock AkShareClient：第二只基金失败
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_compare.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_compare.agent._emit_progress", new_callable=AsyncMock):
            
            mock_get.side_effect = [
                complete_fund_data,
                Exception("Data not available"),
            ]
            mock_skill.return_value = {"payload": {"ok": True, "funds": []}}
            mock_llm.return_value = "【产品对比】数据不足，无法生成对比分析。"
            
            result = await agent.run(question, mock_ctx)
            
            # 验证回退到 skill 逻辑（因为有效基金 < 2）
            mock_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_fund_comparison_insufficient_funds(self, mock_ctx):
        """测试有效基金数量不足场景。"""
        agent = ProductCompareAgent()
        question = "对比基金"  # 没有基金代码
        
        # Mock skill 逻辑
        with patch("agents.fund_agent.product_compare.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_compare.agent._emit_progress", new_callable=AsyncMock):
            
            mock_skill.return_value = {"payload": {"ok": True, "funds": []}}
            mock_llm.return_value = "【产品对比】请提供至少两只基金代码。"
            
            result = await agent.run(question, mock_ctx)
            
            # 验证回退到 skill 逻辑
            mock_skill.assert_called_once()


class TestFallbackMechanism:
    """测试兜底机制。"""

    @pytest.mark.asyncio
    async def test_interpret_fallback_on_akshare_failure(self, mock_ctx):
        """测试 ProductInterpretAgent 在 AkShare 失败时的兜底。"""
        agent = ProductInterpretAgent()
        question = "分析基金 000001"
        
        # Mock 所有可能的失败点
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_interpret.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_interpret.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_interpret.agent._emit_progress", new_callable=AsyncMock):
            
            # AkShare 失败
            mock_get.side_effect = Exception("Service unavailable")
            
            # Skill 也失败
            mock_skill.return_value = None
            
            # LLM 返回兜底信息
            mock_llm.return_value = "【产品解析】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。请先提供基金代码或配置数据获取工具。"
            
            result = await agent.run(question, mock_ctx)
            
            # 验证返回了兜底信息
            assert isinstance(result, str)
            assert "未获取到" in result or "暂无法" in result
            
            # 验证尝试了所有降级路径
            mock_get.assert_called_once()
            mock_skill.assert_called_once()
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_fallback_on_akshare_failure(self, mock_ctx):
        """测试 ProductCompareAgent 在 AkShare 失败时的兜底。"""
        agent = ProductCompareAgent()
        question = "对比 000001 和 110011"
        
        # Mock 所有可能的失败点
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_compare.agent.run_configured_skills", new_callable=AsyncMock) as mock_skill, \
             patch("agents.fund_agent.product_compare.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_compare.agent._emit_progress", new_callable=AsyncMock):
            
            # AkShare 失败
            mock_get.side_effect = Exception("Service unavailable")
            
            # Skill 也失败
            mock_skill.return_value = None
            
            # LLM 返回兜底信息
            mock_llm.return_value = "【产品对比】目前未获取到可用于分析的基金供应商数据，暂无法按要求输出分析结果。请先提供基金供应商数据或配置数据获取工具。"
            
            result = await agent.run(question, mock_ctx)
            
            # 验证返回了兜底信息
            assert isinstance(result, str)
            assert "未获取到" in result or "暂无法" in result
            
            # 验证尝试了所有降级路径
            assert mock_get.call_count == 2  # 尝试获取两只基金
            mock_skill.assert_called_once()
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_structured_output_fallback(self, mock_ctx, complete_fund_data):
        """测试结构化输出失败时的兜底。"""
        agent = ProductInterpretAgent()
        question = "分析基金 000001"
        
        # Mock AkShareClient 和 LLM
        with patch.object(agent.akshare_client, "get_all_data", new_callable=AsyncMock) as mock_get, \
             patch("agents.fund_agent.product_interpret.agent._llm_call_maybe_stream", new_callable=AsyncMock) as mock_llm, \
             patch("agents.fund_agent.product_interpret.agent.build_single_output") as mock_build, \
             patch("agents.fund_agent.product_interpret.agent._emit_progress", new_callable=AsyncMock):
            
            mock_get.return_value = complete_fund_data
            llm_text = "【基本信息】华夏成长..."
            mock_llm.return_value = llm_text
            
            # build_single_output 失败
            mock_build.side_effect = Exception("JSON parsing error")
            
            result = await agent.run(question, mock_ctx)
            
            # 验证返回了 LLM 原始文本（兜底）
            assert result == llm_text


class TestDataValidation:
    """测试数据验证逻辑。"""

    @pytest.mark.asyncio
    async def test_validate_fund_code_format(self, mock_ctx):
        """测试基金代码格式验证。"""
        agent = ProductInterpretAgent()
        
        # 测试有效代码
        assert agent._extract_symbol("分析基金 000001") == "000001"
        
        # 测试无效代码
        assert agent._extract_symbol("分析基金 12345") is None  # 5位
        assert agent._extract_symbol("分析基金 1234567") is None  # 7位
        assert agent._extract_symbol("分析基金 ABC123") is None  # 非数字

    @pytest.mark.asyncio
    async def test_validate_data_completeness(self, mock_ctx, complete_fund_data, incomplete_fund_data):
        """测试数据完整性验证。"""
        agent = ProductInterpretAgent()
        
        # 测试完整数据
        assert agent._has_sufficient_data(complete_fund_data) is True
        
        # 测试不完整数据
        assert agent._has_sufficient_data(incomplete_fund_data) is False
        
        # 测试空数据
        assert agent._has_sufficient_data({}) is False
        assert agent._has_sufficient_data(None) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
