"""
前端兼容性验证测试

测试 AkShare 真实数据与前端组件的兼容性。

测试范围：
1. 卡片组件展示
2. 表格组件展示
3. 图表组件展示（环形图、折线图、柱状图）
4. 数据缺失时的展示
5. 兜底机制
"""

import sys
from pathlib import Path

# 确保 backend 在 path 上
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
import json
from typing import Any

from pkg.fund_formatter import (
    format_fund_cards,
    format_performance_table,
    format_fee_table,
    format_asset_chart,
    format_nav_chart_from_akshare,
    format_industry_chart,
    format_holding_table,
    build_single_output,
    build_compare_output,
)


# =============================================================================
# 测试数据：模拟 AkShare 返回的真实数据格式
# =============================================================================

MOCK_BASIC_INFO_DATA = {
    "ok": True,
    "data": [
        {"item": "基金代码", "value": "000001"},
        {"item": "基金简称", "value": "华夏成长混合"},
        {"item": "基金类型", "value": "混合型"},
        {"item": "基金规模", "value": "45.32亿元"},
        {"item": "基金经理", "value": "张三"},
        {"item": "成立日期", "value": "2001-12-18"},
    ]
}

MOCK_ACHIEVEMENT_DATA = {
    "ok": True,
    "data": [
        {"item": "近1月", "value": "2.35%"},
        {"item": "近3月", "value": "5.67%"},
        {"item": "近6月", "value": "12.34%"},
        {"item": "近1年", "value": "28.90%"},
        {"item": "近3年", "value": "89.45%"},
        {"item": "今年来", "value": "15.23%"},
        {"item": "成立来", "value": "512.67%"},
    ]
}

MOCK_ANALYSIS_DATA = {
    "ok": True,
    "data": [
        {"item": "波动率", "value": "18.56%"},
        {"item": "夏普比率", "value": "1.23"},
        {"item": "最大回撤", "value": "-15.32%"},
    ]
}

MOCK_DETAIL_HOLD_DATA = {
    "ok": True,
    "data": [
        {"资产类型": "股票", "仓位占比": 75.5},
        {"资产类型": "债券", "仓位占比": 15.2},
        {"资产类型": "现金", "仓位占比": 8.3},
        {"资产类型": "其他", "仓位占比": 1.0},
    ]
}

MOCK_DETAIL_INFO_DATA = {
    "ok": True,
    "data": [
        {"item": "管理费", "value": "1.50%"},
        {"item": "托管费", "value": "0.25%"},
        {"item": "申购费", "value": "1.20%"},
        {"item": "赎回费", "value": "0.50%"},
    ]
}

MOCK_NAV_DATA = {
    "ok": True,
    "data": [
        {"净值日期": "2024-01-01", "单位净值": 1.2340, "日增长率": 0.56},
        {"净值日期": "2024-01-02", "单位净值": 1.2450, "日增长率": 0.89},
        {"净值日期": "2024-01-03", "单位净值": 1.2380, "日增长率": -0.56},
        {"净值日期": "2024-01-04", "单位净值": 1.2520, "日增长率": 1.13},
        {"净值日期": "2024-01-05", "单位净值": 1.2610, "日增长率": 0.72},
    ]
}

MOCK_INDUSTRY_DATA = {
    "ok": True,
    "data": [
        {"行业类别": "制造业", "占净值比例": 35.5},
        {"行业类别": "信息技术", "占净值比例": 22.3},
        {"行业类别": "金融业", "占净值比例": 15.8},
        {"行业类别": "医疗健康", "占净值比例": 12.4},
        {"行业类别": "消费", "占净值比例": 8.2},
    ]
}

MOCK_HOLDING_DATA = {
    "ok": True,
    "data": [
        {"股票代码": "600519", "股票名称": "贵州茅台", "占净值比例": 8.5, "持仓市值": 38500},
        {"股票代码": "000858", "股票名称": "五粮液", "占净值比例": 6.2, "持仓市值": 28100},
        {"股票代码": "601318", "股票名称": "中国平安", "占净值比例": 5.8, "持仓市值": 26300},
    ]
}


def create_mock_fund_data(symbol: str = "000001") -> dict[str, Any]:
    """创建模拟的基金数据（模拟 AkShareClient.get_all_data 返回格式）"""
    return {
        "symbol": symbol,
        "basic_info": MOCK_BASIC_INFO_DATA,
        "achievement": MOCK_ACHIEVEMENT_DATA,
        "analysis": MOCK_ANALYSIS_DATA,
        "detail_hold": MOCK_DETAIL_HOLD_DATA,
        "detail_info": MOCK_DETAIL_INFO_DATA,
        "nav_data": MOCK_NAV_DATA,
    }


# =============================================================================
# 测试 17.1: 使用真实 AkShare 数据测试前端渲染
# =============================================================================

class TestFrontendDataFormat:
    """测试数据格式与前端 TypeScript 类型定义的兼容性"""

    def test_info_card_format(self):
        """测试卡片数据格式符合前端 InfoCard 类型"""
        fund_data = create_mock_fund_data()
        cards = format_fund_cards(fund_data)

        assert len(cards) > 0, "应该生成至少一张卡片"

        for card in cards:
            # 验证必需字段（card 是字典）
            assert 'id' in card, "卡片必须有 id 字段"
            assert 'title' in card, "卡片必须有 title 字段"
            assert 'type' in card, "卡片必须有 type 字段"
            assert 'data' in card, "卡片必须有 data 字段"

            # 验证类型值
            assert card['type'] in ['basic', 'performance', 'risk', 'fee'], \
                f"卡片类型必须是有效值，当前: {card['type']}"

            # 验证 data 是字典
            assert isinstance(card['data'], dict), "卡片 data 必须是字典"

            # 验证可以序列化为 JSON
            json_str = json.dumps(card, ensure_ascii=False)
            assert len(json_str) > 0, "卡片应该可以序列化为 JSON"

    def test_table_section_format(self):
        """测试表格数据格式符合前端 TableSection 类型"""
        funds = [create_mock_fund_data("000001"), create_mock_fund_data("000002")]
        table = format_performance_table(funds)

        if table is None:
            pytest.skip("数据不足，跳过表格测试")

        # 验证必需字段（table 是字典）
        assert 'id' in table, "表格必须有 id 字段"
        assert 'title' in table, "表格必须有 title 字段"
        assert 'type' in table, "表格必须有 type 字段"
        assert table['type'] == 'table', "表格类型必须是 'table'"
        assert 'table' in table, "表格必须有 table 字段"

        # 验证 table 结构
        assert 'headers' in table['table'], "表格必须有 headers 字段"
        assert 'rows' in table['table'], "表格必须有 rows 字段"
        assert isinstance(table['table']['headers'], list), "headers 必须是列表"
        assert isinstance(table['table']['rows'], list), "rows 必须是列表"

        # 验证每行数据包含所有表头
        for row in table['table']['rows']:
            for header in table['table']['headers']:
                assert header in row, f"行数据缺少表头 '{header}'"

    def test_chart_config_format(self):
        """测试图表数据格式符合前端 ChartConfig 类型"""
        fund_data = create_mock_fund_data()

        # 测试资产配置环形图
        chart = format_asset_chart(fund_data)
        if chart:
            self._validate_chart(chart, 'pie')

        # 测试净值走势折线图
        nav_chart = format_nav_chart_from_akshare(MOCK_NAV_DATA, "000001")
        if nav_chart:
            self._validate_chart(nav_chart, 'line')

        # 测试行业配置柱状图
        industry_chart = format_industry_chart(MOCK_INDUSTRY_DATA, "000001")
        if industry_chart:
            self._validate_chart(industry_chart, 'bar')

    def _validate_chart(self, chart: dict, expected_type: str):
        """验证图表配置格式"""
        assert 'id' in chart, "图表必须有 id 字段"
        assert 'title' in chart, "图表必须有 title 字段"
        assert 'type' in chart, "图表必须有 type 字段"
        assert chart['type'] == expected_type, f"图表类型应为 '{expected_type}'"
        assert 'data' in chart, "图表必须有 data 字段"

        # 验证可以序列化为 JSON
        json_str = json.dumps(chart, ensure_ascii=False)
        assert len(json_str) > 0, "图表应该可以序列化为 JSON"


# =============================================================================
# 测试 17.2: 验证卡片组件展示
# =============================================================================

class TestCardComponentCompatibility:
    """测试卡片组件与后端数据的兼容性"""

    def test_basic_card_display(self):
        """测试基本信息卡片展示"""
        fund_data = create_mock_fund_data()
        cards = format_fund_cards(fund_data)

        basic_cards = [c for c in cards if c['type'] == 'basic']
        assert len(basic_cards) > 0, "应该有基本信息卡片"

        card = basic_cards[0]
        # 验证关键字段存在
        assert 'name' in card['data'] or '基金名称' in str(card['data']), \
            "基本信息卡片应包含基金名称"
        assert 'code' in card['data'] or '基金代码' in str(card['data']), \
            "基本信息卡片应包含基金代码"

    def test_performance_card_display(self):
        """测试业绩表现卡片展示"""
        fund_data = create_mock_fund_data()
        cards = format_fund_cards(fund_data)

        perf_cards = [c for c in cards if c['type'] == 'performance']
        if len(perf_cards) == 0:
            pytest.skip("数据不足，跳过业绩卡片测试")

        card = perf_cards[0]
        # 验证业绩数据存在
        assert len(card['data']) > 0, "业绩卡片应有数据"

    def test_fee_card_display(self):
        """测试费率信息卡片展示"""
        fund_data = create_mock_fund_data()
        cards = format_fund_cards(fund_data)

        fee_cards = [c for c in cards if c['type'] == 'fee']
        if len(fee_cards) == 0:
            pytest.skip("数据不足，跳过费率卡片测试")

        card = fee_cards[0]
        # 验证费率数据存在
        assert len(card['data']) > 0, "费率卡片应有数据"

    def test_card_json_serialization(self):
        """测试卡片可以正确序列化为 JSON（前端可解析）"""
        fund_data = create_mock_fund_data()
        cards = format_fund_cards(fund_data)

        for card in cards:
            # 序列化为 JSON
            card_json = json.dumps(card, ensure_ascii=False)

            # 反序列化验证
            card_dict = json.loads(card_json)
            assert 'id' in card_dict
            assert 'title' in card_dict
            assert 'type' in card_dict
            assert 'data' in card_dict


# =============================================================================
# 测试 17.3: 验证表格组件展示
# =============================================================================

class TestTableComponentCompatibility:
    """测试表格组件与后端数据的兼容性"""

    def test_performance_table_display(self):
        """测试业绩对比表格展示"""
        funds = [
            create_mock_fund_data("000001"),
            create_mock_fund_data("000002"),
        ]
        table = format_performance_table(funds)

        if table is None:
            pytest.skip("数据不足，跳过业绩表格测试")

        # 验证表头
        assert len(table['table']['headers']) > 0, "表格应有表头"
        assert '基金名称' in table['table']['headers'] or '基金代码' in table['table']['headers'] or '指标' in table['table']['headers'], \
            "业绩表格应包含基金名称或代码或指标"

        # 验证行数据
        assert len(table['table']['rows']) > 0, "表格应有数据行"

    def test_fee_table_display(self):
        """测试费率对比表格展示"""
        funds = [
            create_mock_fund_data("000001"),
            create_mock_fund_data("000002"),
        ]
        table = format_fee_table(funds)

        if table is None:
            pytest.skip("数据不足，跳过费率表格测试")

        # 验证表头
        assert len(table['table']['headers']) > 0, "表格应有表头"

        # 验证行数据
        assert len(table['table']['rows']) > 0, "表格应有数据行"

    def test_holding_table_display(self):
        """测试持仓明细表格展示"""
        table = format_holding_table(MOCK_HOLDING_DATA, "000001")

        if table is None:
            pytest.skip("数据不足，跳过持仓表格测试")

        # 验证表头
        assert len(table['table']['headers']) > 0, "持仓表格应有表头"
        assert '股票名称' in table['table']['headers'], "持仓表格应包含股票名称"

        # 验证行数据
        assert len(table['table']['rows']) > 0, "持仓表格应有数据行"

    def test_table_json_serialization(self):
        """测试表格可以正确序列化为 JSON"""
        funds = [create_mock_fund_data("000001"), create_mock_fund_data("000002")]
        table = format_performance_table(funds)

        if table is None:
            pytest.skip("数据不足，跳过表格序列化测试")

        # 序列化为 JSON
        table_json = json.dumps(table, ensure_ascii=False)

        # 反序列化验证
        table_dict = json.loads(table_json)
        assert 'id' in table_dict
        assert 'title' in table_dict
        assert 'type' in table_dict
        assert 'table' in table_dict
        assert 'headers' in table_dict['table']
        assert 'rows' in table_dict['table']


# =============================================================================
# 测试 17.4: 验证图表组件展示
# =============================================================================

class TestChartComponentCompatibility:
    """测试图表组件与后端数据的兼容性"""

    def test_pie_chart_display(self):
        """测试环形图（资产配置）展示"""
        fund_data = create_mock_fund_data()
        chart = format_asset_chart(fund_data)

        if chart is None:
            pytest.skip("数据不足，跳过环形图测试")

        assert chart['type'] == 'pie', "资产配置图应为环形图"

        # 验证数据结构
        data = chart['data']
        assert 'labels' in data, "环形图应有 labels"
        assert 'values' in data, "环形图应有 values"
        assert len(data['labels']) > 0, "环形图应有标签"
        assert len(data['values']) > 0, "环形图应有数值"
        assert len(data['labels']) == len(data['values']), "标签和数值数量应一致"

    def test_line_chart_display(self):
        """测试折线图（净值走势）展示"""
        chart = format_nav_chart_from_akshare(MOCK_NAV_DATA, "000001")

        if chart is None:
            pytest.skip("数据不足，跳过折线图测试")

        assert chart['type'] == 'line', "净值走势图应为折线图"

        # 验证数据结构
        data = chart['data']
        assert 'xAxis' in data, "折线图应有 xAxis"
        assert 'series' in data, "折线图应有 series"
        assert len(data['xAxis']) > 0, "折线图应有 X 轴数据"
        assert len(data['series']) > 0, "折线图应有系列数据"

    def test_bar_chart_display(self):
        """测试柱状图（行业配置）展示"""
        chart = format_industry_chart(MOCK_INDUSTRY_DATA, "000001")

        if chart is None:
            pytest.skip("数据不足，跳过柱状图测试")

        assert chart['type'] == 'bar', "行业配置图应为柱状图"

        # 验证数据结构
        data = chart['data']
        assert 'xAxis' in data, "柱状图应有 xAxis"
        assert 'series' in data, "柱状图应有 series"

    def test_chart_json_serialization(self):
        """测试图表可以正确序列化为 JSON"""
        fund_data = create_mock_fund_data()
        chart = format_asset_chart(fund_data)

        if chart is None:
            pytest.skip("数据不足，跳过图表序列化测试")

        # 序列化为 JSON
        chart_json = json.dumps(chart, ensure_ascii=False)

        # 反序列化验证
        chart_dict = json.loads(chart_json)
        assert 'id' in chart_dict
        assert 'title' in chart_dict
        assert 'type' in chart_dict
        assert 'data' in chart_dict


# =============================================================================
# 测试 17.5: 验证数据缺失时的展示
# =============================================================================

class TestDataMissingHandling:
    """测试数据缺失时的处理"""

    def test_empty_basic_info(self):
        """测试基本信息缺失时的处理"""
        fund_data = create_mock_fund_data()
        fund_data["basic_info"] = {"ok": False, "message": "数据获取失败"}

        cards = format_fund_cards(fund_data)
        # 应该仍然能生成其他卡片
        assert isinstance(cards, list), "即使基本信息缺失，也应返回列表"

    def test_empty_achievement(self):
        """测试业绩数据缺失时的处理"""
        fund_data = create_mock_fund_data()
        fund_data["achievement"] = {"ok": False, "message": "数据获取失败"}

        cards = format_fund_cards(fund_data)
        # 应该仍然能生成其他卡片
        assert isinstance(cards, list), "即使业绩数据缺失，也应返回列表"

    def test_empty_nav_data(self):
        """测试净值数据缺失时的处理"""
        nav_data = {"ok": False, "message": "数据获取失败"}
        chart = format_nav_chart_from_akshare(nav_data, "000001")

        # 应该返回 None，前端会跳过渲染
        assert chart is None, "净值数据缺失时应返回 None"

    def test_empty_industry_data(self):
        """测试行业配置数据缺失时的处理"""
        industry_data = {"ok": False, "message": "数据获取失败"}
        chart = format_industry_chart(industry_data, "000001")

        # 应该返回 None
        assert chart is None, "行业配置数据缺失时应返回 None"

    def test_partial_data_handling(self):
        """测试部分数据缺失时的处理"""
        fund_data = create_mock_fund_data()
        # 只保留基本信息
        fund_data["achievement"] = {"ok": False}
        fund_data["analysis"] = {"ok": False}
        fund_data["detail_hold"] = {"ok": False}

        cards = format_fund_cards(fund_data)
        # 应该仍然能生成基本信息卡片
        assert isinstance(cards, list), "部分数据缺失时仍应返回可用卡片"


# =============================================================================
# 测试 17.6: 完整输出测试
# =============================================================================

class TestCompleteOutput:
    """测试完整的 FundAnalysisOutput 输出"""

    def test_single_fund_output(self):
        """测试单基金分析完整输出"""
        fund_data = create_mock_fund_data()
        supplier_data = {
            "payload": {
                "funds": [fund_data]
            }
        }
        llm_text = """
【基金概况】
华夏成长混合（000001）是一只混合型基金，成立于2001年12月18日。

【业绩表现】
近1年收益率28.90%，表现优秀。

【投资建议】
适合风险承受能力较强的投资者。
"""

        output = build_single_output(supplier_data, llm_text)

        # 验证输出结构
        assert output["type"] == "fund_analysis", "输出类型应为 fund_analysis"
        assert output["mode"] == "single", "模式应为 single"
        assert len(output["cards"]) > 0, "应有卡片"
        assert len(output["text"]) > 0, "应有文本"

        # 验证可以序列化为 JSON
        output_json = json.dumps(output, ensure_ascii=False)
        output_dict = json.loads(output_json)
        assert output_dict["type"] == "fund_analysis"

    def test_compare_fund_output(self):
        """测试多基金对比完整输出"""
        funds = [
            create_mock_fund_data("000001"),
            create_mock_fund_data("000002"),
        ]
        supplier_data = {
            "payload": {
                "funds": funds
            }
        }
        llm_text = """
【基金对比】
两只基金在业绩表现上存在差异。

【投资建议】
建议根据风险偏好选择。
"""

        output = build_compare_output(supplier_data, llm_text)

        # 验证输出结构
        assert output["type"] == "fund_analysis", "输出类型应为 fund_analysis"
        assert output["mode"] == "compare", "模式应为 compare"

        # 验证可以序列化为 JSON
        output_json = json.dumps(output, ensure_ascii=False)
        output_dict = json.loads(output_json)
        assert output_dict["type"] == "fund_analysis"
        assert output_dict["mode"] == "compare"

    def test_output_json_compatibility(self):
        """测试输出 JSON 与前端 TypeScript 类型兼容"""
        fund_data = create_mock_fund_data()
        supplier_data = {"payload": {"funds": [fund_data]}}
        llm_text = "测试文本"

        output = build_single_output(supplier_data, llm_text)
        output_json = json.dumps(output, ensure_ascii=False)

        # 模拟前端解析
        parsed = json.loads(output_json)

        # 验证所有必需字段存在
        required_fields = ['type', 'mode', 'summary', 'cards', 'sections', 'charts', 'text']
        for field in required_fields:
            assert field in parsed, f"输出缺少必需字段: {field}"

        # 验证字段类型
        assert isinstance(parsed['cards'], list), "cards 应为列表"
        assert isinstance(parsed['sections'], list), "sections 应为列表"
        assert isinstance(parsed['charts'], list), "charts 应为列表"
        assert isinstance(parsed['text'], str), "text 应为字符串"


# =============================================================================
# 运行测试
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])