"""fund_formatter 单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保 backend 在 path 上
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from pkg.fund_formatter import (
    build_compare_output,
    build_single_output,
    extract_text_for_compliance,
    format_asset_chart,
    format_fund_cards,
    format_holding_table,
    format_industry_chart,
    format_nav_chart,
    format_nav_chart_from_akshare,
    format_performance_table,
    format_standard_14_fields_table,
    format_style_radar,
    try_parse_fund_analysis,
)
from pkg.fund_types import is_fund_analysis


# ---------------------------------------------------------------------------
# 测试 fixture
# ---------------------------------------------------------------------------

def _make_interpret_fund(sym: str = "000044") -> dict:
    return {
        "symbol": sym,
        "basic_info": {
            "ok": True,
            "data": [
                {"item": "基金简称", "value": "嘉实美国成长股票(QDII)"},
                {"item": "基金代码", "value": sym},
                {"item": "基金类型", "value": "QDII"},
                {"item": "基金经理", "value": "张自力"},
                {"item": "基金规模", "value": "12.5亿"},
                {"item": "风险等级", "value": "R3-中风险"},
                {"item": "管理费率", "value": "1.50%"},
                {"item": "托管费率", "value": "0.25%"},
            ],
        },
        "achievement": {
            "ok": True,
            "data": [
                {"item": "近1月", "value": "2.5%"},
                {"item": "近3月", "value": "8.3%"},
                {"item": "近1年", "value": "15.2%"},
                {"item": "近3年", "value": "45.7%"},
                {"item": "夏普比率", "value": "1.25"},
                {"item": "最大回撤", "value": "-12.34%"},
            ],
        },
        "analysis": {
            "ok": True,
            "data": [
                {"item": "股票", "value": "85.5"},
                {"item": "债券", "value": "8.2"},
                {"item": "现金", "value": "4.3"},
                {"item": "其他", "value": "2.0"},
            ],
        },
        "detail_info": {"ok": False, "message": "不可用"},
        "detail_hold": {"ok": False, "message": "不可用"},
        "profit_probability": {"ok": False, "message": "不可用"},
        "risk": {"ok": False, "message": "不可用"},
    }


def _make_compare_fund(sym: str = "000044") -> dict:
    return {
        "symbol": sym,
        "basic_info": {
            "ok": True,
            "data": [
                {"item": "基金简称", "value": f"测试基金{sym}"},
                {"item": "基金代码", "value": sym},
                {"item": "基金类型", "value": "股票型"},
                {"item": "基金经理", "value": "张三"},
                {"item": "基金规模", "value": "10亿"},
                {"item": "管理费率", "value": "1.50%"},
            ],
        },
        "performance": {
            "achievement": {
                "ok": True,
                "data": [
                    {"item": "近1月", "value": "2.5%"},
                    {"item": "近3月", "value": "8.0%"},
                    {"item": "近1年", "value": "15.0%"},
                    {"item": "近3年", "value": "40.0%"},
                ],
            },
            "profit_probability": {"ok": False, "message": "不可用"},
        },
        "asset_allocation": {
            "ok": True,
            "data": {"top_holdings": [
                {"股票名称": "贵州茅台", "占净值比例": "8.5"},
                {"股票名称": "宁德时代", "占净值比例": "6.2"},
            ]},
        },
        "risk": {"ok": False, "message": "不可用"},
    }


SAMPLE_LLM_TEXT = """
【基本信息】
000044 嘉实美国成长股票(QDII)，QDII 型基金，基金经理张自力，规模12.5亿，R3中风险。

【业绩表现】
近1年收益15.2%，近3年收益45.7%，夏普比率1.25。

【分析结论】
该基金长期表现优异，适合风险承受能力较高的投资者。

【风险提示】
基金有风险，投资需谨慎。以上内容由AI生成，仅供参考。
""".strip()


# ---------------------------------------------------------------------------
# format_fund_cards
# ---------------------------------------------------------------------------

class TestFormatFundCards:
    def test_normal_interpret_fund(self):
        fund = _make_interpret_fund()
        cards = format_fund_cards(fund)
        assert len(cards) >= 2  # basic + performance
        types = {c["type"] for c in cards}
        assert "basic" in types
        assert "performance" in types

    def test_normal_compare_fund(self):
        fund = _make_compare_fund()
        cards = format_fund_cards(fund)
        assert len(cards) >= 1
        assert any(c["type"] == "basic" for c in cards)

    def test_all_modules_failed(self):
        fund = {
            "symbol": "999999",
            "basic_info": {"ok": False, "message": "失败"},
            "achievement": {"ok": False, "message": "失败"},
        }
        cards = format_fund_cards(fund)
        assert cards == []

    def test_empty_data(self):
        fund = {"symbol": "111111", "basic_info": {"ok": True, "data": []}}
        cards = format_fund_cards(fund)
        assert cards == []


# ---------------------------------------------------------------------------
# format_performance_table
# ---------------------------------------------------------------------------

class TestFormatPerformanceTable:
    def test_two_funds(self):
        funds = [_make_compare_fund("000044"), _make_compare_fund("000042")]
        table = format_performance_table(funds)
        assert table is not None
        assert table["type"] == "table"
        assert "000044" in table["table"]["headers"]
        assert "000042" in table["table"]["headers"]
        assert len(table["table"]["rows"]) > 0

    def test_no_data(self):
        funds = [
            {"symbol": "111", "performance": {"achievement": {"ok": False}}},
            {"symbol": "222", "performance": {"achievement": {"ok": False}}},
        ]
        table = format_performance_table(funds)
        assert table is None

    def test_single_fund(self):
        funds = [_make_interpret_fund()]
        table = format_performance_table(funds)
        assert table is not None
        assert len(table["table"]["headers"]) == 2


# ---------------------------------------------------------------------------
# format_asset_chart
# ---------------------------------------------------------------------------

class TestFormatAssetChart:
    def test_from_analysis(self):
        fund = _make_interpret_fund()
        chart = format_asset_chart(fund)
        assert chart is not None
        assert chart["type"] == "donut"
        assert len(chart["data"]["series"]) == 4

    def test_no_data(self):
        fund = {"symbol": "999", "analysis": {"ok": False}}
        chart = format_asset_chart(fund)
        assert chart is None


# ---------------------------------------------------------------------------
# format_nav_chart_from_akshare
# ---------------------------------------------------------------------------

class TestFormatNavChartFromAkshare:
    def test_normal_nav_data(self):
        """测试正常的净值数据"""
        nav_data = {
            "ok": True,
            "data": [
                {"净值日期": "2024-01-01", "单位净值": 1.0},
                {"净值日期": "2024-01-02", "单位净值": 1.05},
                {"净值日期": "2024-01-03", "单位净值": 1.08},
                {"净值日期": "2024-01-04", "单位净值": 1.12},
                {"净值日期": "2024-01-05", "单位净值": 1.15},
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000001")
        
        assert chart is not None
        assert chart["type"] == "line"
        assert chart["id"] == "nav_000001"
        assert chart["title"] == "净值走势"
        assert len(chart["data"]["xAxis"]) == 5
        assert len(chart["data"]["series"]) == 1
        assert chart["data"]["series"][0]["name"] == "000001"
        
        # 验证收益率计算正确（基准 1.0）
        returns = chart["data"]["series"][0]["data"]
        assert returns[0] == 0.0  # (1.0 / 1.0 - 1) * 100
        assert abs(returns[1] - 5.0) < 0.01  # (1.05 / 1.0 - 1) * 100
        assert abs(returns[4] - 15.0) < 0.01  # (1.15 / 1.0 - 1) * 100
    
    def test_alternative_field_names(self):
        """测试备用字段名（日期、净值）"""
        nav_data = {
            "ok": True,
            "data": [
                {"日期": "2024-01-01", "净值": 1.0},
                {"日期": "2024-01-02", "净值": 1.10},
                {"日期": "2024-01-03", "净值": 1.20},
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000002")
        
        assert chart is not None
        assert len(chart["data"]["xAxis"]) == 3
        returns = chart["data"]["series"][0]["data"]
        assert abs(returns[2] - 20.0) < 0.01
    
    def test_data_downsampling(self):
        """测试数据降采样（超过 100 个点）"""
        # 生成 250 个数据点
        data_points = [
            {"净值日期": f"2024-{i//30+1:02d}-{i%30+1:02d}", "单位净值": 1.0 + i * 0.01}
            for i in range(250)
        ]
        nav_data = {"ok": True, "data": data_points}
        
        chart = format_nav_chart_from_akshare(nav_data, "000003")
        
        assert chart is not None
        # 应该降采样到最多 100 个点
        assert len(chart["data"]["xAxis"]) <= 100
        assert len(chart["data"]["series"][0]["data"]) <= 100
    
    def test_insufficient_data(self):
        """测试数据不足（少于 2 个点）"""
        nav_data = {
            "ok": True,
            "data": [{"净值日期": "2024-01-01", "单位净值": 1.0}]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000004")
        assert chart is None
    
    def test_ok_false(self):
        """测试 ok=False 的情况"""
        nav_data = {"ok": False, "message": "数据获取失败"}
        chart = format_nav_chart_from_akshare(nav_data, "000005")
        assert chart is None
    
    def test_invalid_nav_data(self):
        """测试无效的 nav_data"""
        assert format_nav_chart_from_akshare(None, "000006") is None
        assert format_nav_chart_from_akshare({}, "000007") is None
        assert format_nav_chart_from_akshare({"ok": True}, "000008") is None
    
    def test_base_nav_zero(self):
        """测试基准净值为 0 的情况"""
        nav_data = {
            "ok": True,
            "data": [
                {"净值日期": "2024-01-01", "单位净值": 0},
                {"净值日期": "2024-01-02", "单位净值": 1.0},
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000009")
        assert chart is None
    
    def test_base_nav_negative(self):
        """测试基准净值为负数的情况"""
        nav_data = {
            "ok": True,
            "data": [
                {"净值日期": "2024-01-01", "单位净值": -1.0},
                {"净值日期": "2024-01-02", "单位净值": 1.0},
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000010")
        assert chart is None
    
    def test_mixed_valid_invalid_records(self):
        """测试混合有效和无效记录"""
        nav_data = {
            "ok": True,
            "data": [
                {"净值日期": "2024-01-01", "单位净值": 1.0},
                "invalid_record",  # 无效记录
                {"净值日期": "2024-01-02", "单位净值": 1.05},
                {"净值日期": None, "单位净值": 1.10},  # 缺少日期
                {"净值日期": "2024-01-03", "单位净值": None},  # 缺少净值
                {"净值日期": "2024-01-04", "单位净值": 1.15},
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000011")
        
        assert chart is not None
        # 应该只保留有效的 3 个记录
        assert len(chart["data"]["xAxis"]) == 3
    
    def test_chart_options(self):
        """测试图表配置选项"""
        nav_data = {
            "ok": True,
            "data": [
                {"净值日期": "2024-01-01", "单位净值": 1.0},
                {"净值日期": "2024-01-02", "单位净值": 1.05},
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000012")
        
        assert chart is not None
        assert chart["options"]["showLegend"] is True
        assert chart["options"]["showGrid"] is True
        assert chart["options"]["yAxisLabel"] == "累计收益率(%)"
    
    def test_description_format(self):
        """测试描述信息格式"""
        nav_data = {
            "ok": True,
            "data": [
                {"净值日期": f"2024-01-{i:02d}", "单位净值": 1.0 + i * 0.01}
                for i in range(1, 11)
            ]
        }
        chart = format_nav_chart_from_akshare(nav_data, "000013")
        
        assert chart is not None
        assert "近10个交易日" in chart["description"]


# ---------------------------------------------------------------------------
# format_industry_chart
# ---------------------------------------------------------------------------

class TestFormatIndustryChart:
    def test_normal_industry_data(self):
        """测试正常的行业配置数据"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业类别": "制造业", "占净值比例": 25.5},
                {"行业类别": "金融业", "占净值比例": 18.3},
                {"行业类别": "信息技术", "占净值比例": 15.2},
                {"行业类别": "医药生物", "占净值比例": 12.8},
                {"行业类别": "消费", "占净值比例": 10.5},
            ]
        }
        chart = format_industry_chart(industry_data, "000001")
        
        assert chart is not None
        assert chart["type"] == "bar"
        assert chart["id"] == "industry_000001"
        assert chart["title"] == "行业配置"
        assert len(chart["data"]["xAxis"]) == 5
        assert len(chart["data"]["series"]) == 1
        assert chart["data"]["series"][0]["name"] == "占净值比例"
        
        # 验证按占比降序排列
        values = chart["data"]["series"][0]["data"]
        assert values[0] == 25.5  # 制造业
        assert values[1] == 18.3  # 金融业
        assert values[4] == 10.5  # 消费
    
    def test_alternative_field_names(self):
        """测试备用字段名"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业名称": "制造业", "占比": 25.5},
                {"行业": "金融业", "比例": 18.3},
                {"industry": "IT", "ratio": 15.2},
            ]
        }
        chart = format_industry_chart(industry_data, "000002")
        
        assert chart is not None
        assert len(chart["data"]["xAxis"]) == 3
        assert "制造业" in chart["data"]["xAxis"]
        assert "金融业" in chart["data"]["xAxis"]
        assert "IT" in chart["data"]["xAxis"]
    
    def test_top_10_industries(self):
        """测试取前 10 大行业"""
        # 生成 15 个行业数据
        data_points = [
            {"行业类别": f"行业{i}", "占净值比例": 20.0 - i}
            for i in range(15)
        ]
        industry_data = {"ok": True, "data": data_points}
        
        chart = format_industry_chart(industry_data, "000003")
        
        assert chart is not None
        # 应该只保留前 10 大行业
        assert len(chart["data"]["xAxis"]) == 10
        assert len(chart["data"]["series"][0]["data"]) == 10
        
        # 验证是前 10 大
        values = chart["data"]["series"][0]["data"]
        assert values[0] == 20.0  # 行业0
        assert values[9] == 11.0  # 行业9
    
    def test_sorting_by_ratio(self):
        """测试按占比排序"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业类别": "A", "占净值比例": 10.0},
                {"行业类别": "B", "占净值比例": 30.0},
                {"行业类别": "C", "占净值比例": 20.0},
                {"行业类别": "D", "占净值比例": 5.0},
            ]
        }
        chart = format_industry_chart(industry_data, "000004")
        
        assert chart is not None
        labels = chart["data"]["xAxis"]
        values = chart["data"]["series"][0]["data"]
        
        # 验证降序排列
        assert labels[0] == "B"
        assert values[0] == 30.0
        assert labels[1] == "C"
        assert values[1] == 20.0
        assert labels[2] == "A"
        assert values[2] == 10.0
        assert labels[3] == "D"
        assert values[3] == 5.0
    
    def test_empty_data(self):
        """测试空数据"""
        industry_data = {"ok": True, "data": []}
        chart = format_industry_chart(industry_data, "000005")
        assert chart is None
    
    def test_ok_false(self):
        """测试 ok=False 的情况"""
        industry_data = {"ok": False, "message": "数据获取失败"}
        chart = format_industry_chart(industry_data, "000006")
        assert chart is None
    
    def test_invalid_industry_data(self):
        """测试无效的 industry_data"""
        assert format_industry_chart(None, "000007") is None
        assert format_industry_chart({}, "000008") is None
        assert format_industry_chart({"ok": True}, "000009") is None
        assert format_industry_chart({"ok": True, "data": "not_a_list"}, "000010") is None
    
    def test_mixed_valid_invalid_records(self):
        """测试混合有效和无效记录"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业类别": "制造业", "占净值比例": 25.5},
                "invalid_record",  # 无效记录
                {"行业类别": "金融业", "占净值比例": 18.3},
                {"行业类别": None, "占净值比例": 15.0},  # 缺少行业名
                {"行业类别": "IT", "占净值比例": None},  # 缺少占比
                {"行业类别": "医药", "占净值比例": 12.8},
            ]
        }
        chart = format_industry_chart(industry_data, "000011")
        
        assert chart is not None
        # 应该只保留有效的 3 个记录
        assert len(chart["data"]["xAxis"]) == 3
        assert "制造业" in chart["data"]["xAxis"]
        assert "金融业" in chart["data"]["xAxis"]
        assert "医药" in chart["data"]["xAxis"]
    
    def test_chart_options(self):
        """测试图表配置选项"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业类别": "制造业", "占净值比例": 25.5},
                {"行业类别": "金融业", "占净值比例": 18.3},
            ]
        }
        chart = format_industry_chart(industry_data, "000012")
        
        assert chart is not None
        assert chart["options"]["showLegend"] is False
        assert chart["options"]["showGrid"] is True
        assert chart["options"]["yAxisLabel"] == "占净值比例(%)"
    
    def test_description_format(self):
        """测试描述信息格式"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业类别": f"行业{i}", "占净值比例": 10.0 - i}
                for i in range(5)
            ]
        }
        chart = format_industry_chart(industry_data, "000013")
        
        assert chart is not None
        assert "前5大行业配置" in chart["description"]
    
    def test_string_ratio_values(self):
        """测试字符串类型的占比值"""
        industry_data = {
            "ok": True,
            "data": [
                {"行业类别": "制造业", "占净值比例": "25.5"},
                {"行业类别": "金融业", "占净值比例": "18.3%"},
                {"行业类别": "IT", "占净值比例": 15.2},
            ]
        }
        chart = format_industry_chart(industry_data, "000014")
        
        assert chart is not None
        values = chart["data"]["series"][0]["data"]
        assert abs(values[0] - 25.5) < 0.01
        assert abs(values[1] - 18.3) < 0.01
        assert abs(values[2] - 15.2) < 0.01


# ---------------------------------------------------------------------------
# format_holding_table
# ---------------------------------------------------------------------------

class TestFormatHoldingTable:
    def test_normal_holding_data(self):
        """测试正常的持仓明细数据"""
        holding_data = {
            "ok": True,
            "data": [
                {"股票代码": "600519", "股票名称": "贵州茅台", "占净值比例": 8.5, "持仓市值": 12500.0},
                {"股票代码": "300750", "股票名称": "宁德时代", "占净值比例": 6.2, "持仓市值": 9800.0},
                {"股票代码": "000858", "股票名称": "五粮液", "占净值比例": 5.3, "持仓市值": 7500.0},
                {"股票代码": "600036", "股票名称": "招商银行", "占净值比例": 4.8, "持仓市值": 6800.0},
                {"股票代码": "601318", "股票名称": "中国平安", "占净值比例": 4.2, "持仓市值": 6000.0},
            ]
        }
        table = format_holding_table(holding_data, "000001")
        
        assert table is not None
        assert table["type"] == "table"
        assert table["id"] == "holding_000001"
        assert table["title"] == "前十大重仓股"
        assert len(table["table"]["rows"]) == 5
        assert "序号" in table["table"]["headers"]
        assert "股票代码" in table["table"]["headers"]
        assert "股票名称" in table["table"]["headers"]
        assert "占净值比例" in table["table"]["headers"]
        assert "持仓市值" in table["table"]["headers"]
        
        # 验证第一行数据
        first_row = table["table"]["rows"][0]
        assert first_row["序号"] == 1
        assert first_row["股票代码"] == "600519"
        assert first_row["股票名称"] == "贵州茅台"
        assert first_row["占净值比例"] == "8.50%"
        assert "1.25亿元" in first_row["持仓市值"]
    
    def test_alternative_field_names(self):
        """测试备用字段名"""
        holding_data = {
            "ok": True,
            "data": [
                {"代码": "600519", "名称": "贵州茅台", "占比": 8.5, "市值": 12500.0},
                {"code": "300750", "name": "宁德时代", "比例": 6.2, "value": 9800.0},
            ]
        }
        table = format_holding_table(holding_data, "000002")
        
        assert table is not None
        assert len(table["table"]["rows"]) == 2
        assert table["table"]["rows"][0]["股票代码"] == "600519"
        assert table["table"]["rows"][1]["股票名称"] == "宁德时代"
    
    def test_top_10_holdings(self):
        """测试取前 10 大重仓股"""
        # 生成 15 只股票
        data_points = [
            {"股票代码": f"60{i:04d}", "股票名称": f"股票{i}", "占净值比例": 10.0 - i * 0.5}
            for i in range(15)
        ]
        holding_data = {"ok": True, "data": data_points}
        
        table = format_holding_table(holding_data, "000003")
        
        assert table is not None
        # 应该只保留前 10 只
        assert len(table["table"]["rows"]) == 10
        assert table["table"]["rows"][0]["股票名称"] == "股票0"
        assert table["table"]["rows"][9]["股票名称"] == "股票9"
    
    def test_market_value_formatting(self):
        """测试市值格式化"""
        holding_data = {
            "ok": True,
            "data": [
                {"股票名称": "股票A", "占净值比例": 8.5, "持仓市值": 15000.0},  # >= 10000 万元 -> 亿元
                {"股票名称": "股票B", "占净值比例": 6.2, "持仓市值": 5000.0},   # < 10000 万元
                {"股票名称": "股票C", "占净值比例": 5.0, "持仓市值": None},     # 无市值
            ]
        }
        table = format_holding_table(holding_data, "000004")
        
        assert table is not None
        rows = table["table"]["rows"]
        assert "1.50亿元" in rows[0]["持仓市值"]
        assert "5000.00万元" in rows[1]["持仓市值"]
        assert rows[2]["持仓市值"] == "-"
    
    def test_missing_fields(self):
        """测试缺失字段"""
        holding_data = {
            "ok": True,
            "data": [
                {"股票代码": "600519", "股票名称": "贵州茅台"},  # 缺少占比和市值
                {"股票名称": "宁德时代", "占净值比例": 6.2},     # 缺少代码和市值
                {"股票代码": "000858"},                         # 只有代码
            ]
        }
        table = format_holding_table(holding_data, "000005")
        
        assert table is not None
        rows = table["table"]["rows"]
        assert len(rows) == 3
        assert rows[0]["占净值比例"] == "-"
        assert rows[0]["持仓市值"] == "-"
        assert "股票代码" not in rows[1]  # 没有代码字段
        assert "股票名称" not in rows[2]  # 没有名称字段（只有代码）
    
    def test_empty_data(self):
        """测试空数据"""
        holding_data = {"ok": True, "data": []}
        table = format_holding_table(holding_data, "000006")
        assert table is None
    
    def test_ok_false(self):
        """测试 ok=False 的情况"""
        holding_data = {"ok": False, "message": "数据获取失败"}
        table = format_holding_table(holding_data, "000007")
        assert table is None
    
    def test_invalid_holding_data(self):
        """测试无效的 holding_data"""
        assert format_holding_table(None, "000008") is None
        assert format_holding_table({}, "000009") is None
        assert format_holding_table({"ok": True}, "000010") is None
        assert format_holding_table({"ok": True, "data": "not_a_list"}, "000011") is None
    
    def test_invalid_records(self):
        """测试无效记录"""
        holding_data = {
            "ok": True,
            "data": [
                "invalid_record",  # 无效记录
                {},                # 空字典（没有股票代码和名称）
                {"占净值比例": 5.0},  # 只有占比，没有股票信息
            ]
        }
        table = format_holding_table(holding_data, "000012")
        assert table is None  # 所有记录都无效
    
    def test_mixed_valid_invalid_records(self):
        """测试混合有效和无效记录"""
        holding_data = {
            "ok": True,
            "data": [
                {"股票代码": "600519", "股票名称": "贵州茅台", "占净值比例": 8.5},
                "invalid_record",
                {"股票名称": "宁德时代", "占净值比例": 6.2},
                {},  # 无效
                {"股票代码": "000858", "股票名称": "五粮液", "占净值比例": 5.3},
            ]
        }
        table = format_holding_table(holding_data, "000013")
        
        assert table is not None
        # 应该只保留有效的 3 条记录
        assert len(table["table"]["rows"]) == 3
    
    def test_dynamic_headers(self):
        """测试动态表头生成"""
        # 只有股票名称，没有代码
        holding_data = {
            "ok": True,
            "data": [
                {"股票名称": "贵州茅台", "占净值比例": 8.5},
                {"股票名称": "宁德时代", "占净值比例": 6.2},
            ]
        }
        table = format_holding_table(holding_data, "000014")
        
        assert table is not None
        headers = table["table"]["headers"]
        assert "序号" in headers
        assert "股票代码" not in headers  # 没有代码字段
        assert "股票名称" in headers
        assert "占净值比例" in headers
        assert "持仓市值" in headers
    
    def test_string_ratio_values(self):
        """测试字符串类型的占比值"""
        holding_data = {
            "ok": True,
            "data": [
                {"股票名称": "贵州茅台", "占净值比例": "8.5"},
                {"股票名称": "宁德时代", "占净值比例": "6.2%"},
                {"股票名称": "五粮液", "占净值比例": 5.3},
            ]
        }
        table = format_holding_table(holding_data, "000015")
        
        assert table is not None
        rows = table["table"]["rows"]
        assert rows[0]["占净值比例"] == "8.50%"
        assert rows[1]["占净值比例"] == "6.20%"
        assert rows[2]["占净值比例"] == "5.30%"


# ---------------------------------------------------------------------------
# format_nav_chart
# ---------------------------------------------------------------------------

class TestFormatNavChart:
    def test_multi_fund(self):
        funds = [_make_interpret_fund("000044"), _make_interpret_fund("000042")]
        chart = format_nav_chart(funds)
        assert chart is not None
        assert chart["type"] == "line"
        assert len(chart["data"]["series"]) == 2

    def test_single_fund(self):
        funds = [_make_interpret_fund()]
        chart = format_nav_chart(funds)
        assert chart is not None

    def test_no_data(self):
        funds = [{"symbol": "999", "achievement": {"ok": False}}]
        chart = format_nav_chart(funds)
        assert chart is None


# ---------------------------------------------------------------------------
# build_single_output
# ---------------------------------------------------------------------------

class TestBuildSingleOutput:
    def test_normal(self):
        supplier_data = {
            "skill": "product_interpret",
            "payload": {"ok": True, "mode": "single", "symbols": ["000044"], "funds": [_make_interpret_fund()]},
        }
        result = build_single_output(supplier_data, SAMPLE_LLM_TEXT)
        assert is_fund_analysis(result)
        assert result["mode"] == "single"
        assert result["text"] == SAMPLE_LLM_TEXT
        # cards 已按需求关闭
        assert result["cards"] == []
        assert len(result["sections"]) > 0
        assert result["summary"]

    def test_empty_supplier_data(self):
        result = build_single_output(None, SAMPLE_LLM_TEXT)
        assert is_fund_analysis(result)
        assert result["cards"] == []
        assert len(result["sections"]) > 0

    def test_empty_llm_text(self):
        supplier_data = {
            "skill": "product_interpret",
            "payload": {"ok": True, "funds": [_make_interpret_fund()]},
        }
        result = build_single_output(supplier_data, "")
        assert is_fund_analysis(result)
        assert result["cards"] == []
        # 即使 LLM 文本为空，也会有14字段表格
        assert len(result["sections"]) > 0
        # 验证第一个 section 是14字段表格
        assert result["sections"][0]["type"] == "table"
        assert "详细信息" in result["sections"][0]["title"]

    def test_serializable(self):
        supplier_data = {
            "skill": "product_interpret",
            "payload": {"ok": True, "funds": [_make_interpret_fund()]},
        }
        result = build_single_output(supplier_data, SAMPLE_LLM_TEXT)
        s = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(s)
        assert is_fund_analysis(parsed)


class TestFormatStandardDetailTable:
    def test_contains_fee_field_with_redemption_tiers(self):
        fund = {
            "symbol": "000046",
            "basic_info": {
                "ok": True,
                "data": [
                    {"item": "基金代码", "value": "000046"},
                    {"item": "基金简称", "value": "工银产业债券B"},
                    {"item": "基金类型", "value": "债券型-普通债券"},
                ],
            },
            "detail_info": {
                "ok": True,
                "data": [
                    {"item": "管理费率", "value": "0.6%/年"},
                    {"item": "托管费率", "value": "0.2%/年"},
                    {"item": "销售服务费率", "value": "0.4%/年"},
                    {"item": "持有7天内赎回收取", "value": "1.5%费用"},
                    {"item": "持有7-30天收取", "value": "0.75%费用"},
                    {"item": "持有30天以上免收赎回费", "value": ""},
                ],
            },
        }

        table = format_standard_14_fields_table(fund)
        assert table is not None
        rows = table["table"]["rows"]
        fee_row = next((r for r in rows if r.get("字段") == "费率"), None)
        assert fee_row is not None
        assert (
            fee_row["内容"]
            == "费率方面：管理费0.6%/年，托管费0.2%/年，销售服务费0.4%/年；"
               "持有7天内赎回收取1.5%费用，持有7-30天收取0.75%费用，持有30天以上免收赎回费。"
        )

    def test_fee_field_compatible_with_akshare_detail_schema(self):
        fund = {
            "symbol": "000058",
            "basic_info": {
                "ok": True,
                "data": [
                    {"item": "基金代码", "value": "000058"},
                    {"item": "基金简称", "value": "国联安安泰灵活配置混合A"},
                ],
            },
            "detail_info": {
                "ok": True,
                "data": [
                    {"费用类型": "其他费用", "条件或名称": "基金管理费", "费率": "0.9%/年"},
                    {"费用类型": "其他费用", "条件或名称": "基金托管费", "费率": "0.2%/年"},
                    {"费用类型": "其他费用", "条件或名称": "销售服务费", "费率": "0.4%/年"},
                    {"费用类型": "赎回费", "条件或名称": "持有7天内赎回收取", "费率": "1.5%费用"},
                    {"费用类型": "赎回费", "条件或名称": "持有7-30天收取", "费率": "0.75%费用"},
                    {"费用类型": "赎回费", "条件或名称": "持有30天以上免收赎回费", "费率": ""},
                ],
            },
        }

        table = format_standard_14_fields_table(fund)
        assert table is not None
        rows = table["table"]["rows"]
        fee_row = next((r for r in rows if r.get("字段") == "费率"), None)
        assert fee_row is not None
        assert fee_row["内容"] != "-"
        assert (
            fee_row["内容"]
            == "费率方面：管理费0.9%/年，托管费0.2%/年，销售服务费0.4%/年；"
               "持有7天内赎回收取1.5%费用，持有7-30天收取0.75%费用，持有30天以上免收赎回费。"
        )


# ---------------------------------------------------------------------------
# build_compare_output
# ---------------------------------------------------------------------------

class TestBuildCompareOutput:
    def test_normal(self):
        supplier_data = {
            "skill": "product_compare",
            "payload": {
                "ok": True,
                "symbols": ["000044", "000042"],
                "funds": [_make_compare_fund("000044"), _make_compare_fund("000042")],
            },
        }
        result = build_compare_output(supplier_data, SAMPLE_LLM_TEXT)
        assert is_fund_analysis(result)
        assert result["mode"] == "compare"
        assert result["cards"] == []
        # 应有对比表格
        table_sections = [s for s in result["sections"] if s.get("type") == "table"]
        assert len(table_sections) >= 1

    def test_empty_supplier(self):
        result = build_compare_output(None, "对比分析文本")
        assert is_fund_analysis(result)
        assert result["cards"] == []


# ---------------------------------------------------------------------------
# try_parse_fund_analysis / extract_text_for_compliance
# ---------------------------------------------------------------------------

class TestParsing:
    def test_valid_json(self):
        obj = {"type": "fund_analysis", "mode": "single", "summary": "", "cards": [], "sections": [], "charts": [], "text": "hello"}
        text = json.dumps(obj)
        parsed = try_parse_fund_analysis(text)
        assert parsed is not None
        assert parsed["text"] == "hello"

    def test_invalid_json(self):
        assert try_parse_fund_analysis("not json") is None
        assert try_parse_fund_analysis('{"type": "other"}') is None
        assert try_parse_fund_analysis("") is None
        assert try_parse_fund_analysis(None) is None  # type: ignore

    def test_extract_text_for_compliance_json(self):
        obj = {"type": "fund_analysis", "mode": "single", "summary": "sum", "cards": [], "sections": [], "charts": [], "text": "hello world"}
        text = json.dumps(obj)
        assert extract_text_for_compliance(text) == "hello world"

    def test_extract_text_for_compliance_plain(self):
        assert extract_text_for_compliance("plain text") == "plain text"
