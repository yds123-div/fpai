# 基金对比报告增强功能

## 概述

本次改进为基金对比报告增加了更丰富的图表类型和更详细的表格指标，提升了报告的可视化效果和信息完整性。

## 新增功能

### 1. 新增图表类型

#### 1.1 收益率柱状图 (Bar Chart)
- **ID**: `return_bar`
- **标题**: "各期收益率对比"
- **展示内容**: 各基金在不同时间段（近1月、近3月、近6月、近1年）的收益率对比
- **用途**: 直观对比不同基金的短期和中期收益表现

#### 1.2 风险指标柱状图 (Bar Chart)
- **ID**: `risk_indicator`
- **标题**: "风险指标对比"
- **展示内容**: 最大回撤、波动率、夏普比率
- **用途**: 对比各基金的风险控制能力和风险调整后收益

#### 1.3 费率环形图 (Donut Chart)
- **ID**: `fee_donut_{基金代码}`
- **标题**: "{基金代码} 费率结构"
- **展示内容**: 管理费率、托管费率、销售服务费率、申购费率
- **用途**: 展示单只基金的费用结构组成

### 2. 新增表格

#### 2.1 基本信息对比表
- **ID**: `basic_info_compare`
- **标题**: "基本信息对比"
- **包含字段**:
  - 基金全称
  - 基金简称
  - 基金类型
  - 基金规模
  - 成立日期
  - 基金经理
  - 基金公司
  - 托管银行
  - 风险等级
  - 晨星评级
  - 投资风格
  - 业绩比较基准
  - 跟踪标的

### 3. 增强现有表格

#### 3.1 业绩对比表增强
- **原有指标**: 近1月、近3月、近6月、近1年、近3年、今年来、成立来、夏普比率、最大回撤、波动率
- **新增指标**:
  - 近2年、近5年收益率
  - 索提诺比率、卡玛比率
  - 年化收益、年化波动
  - 信息比率、跟踪误差
  - 阿尔法、贝塔、R平方
- **显示数量**: 从15个指标增加到25个指标

## 图表展示顺序

在 `build_compare_output` 函数中，图表按以下顺序展示：

1. 净值走势折线图 (Line Chart) - 展示长期趋势
2. 收益率柱状图 (Bar Chart) - 展示各期收益对比
3. 风险指标柱状图 (Bar Chart) - 展示风险指标对比
4. 投资风格雷达图 (Radar Chart) - 展示投资风格差异
5. 资产配置饼图 (Pie Chart) - 每只基金一个，展示资产配置
6. 费率环形图 (Donut Chart) - 第一只基金的费率结构

## 表格展示顺序

1. 基本信息对比表
2. 业绩对比表
3. 费率对比表

## 技术实现

### 新增函数

```python
# 表格生成
format_basic_info_table(funds: list[dict[str, Any]]) -> TableSection | None

# 图表生成
format_return_bar_chart(funds: list[dict[str, Any]]) -> ChartConfig | None
format_fee_donut_chart(funds: list[dict[str, Any]]) -> ChartConfig | None
format_risk_indicator_chart(funds: list[dict[str, Any]]) -> ChartConfig | None
```

### 数据格式要求

所有函数都遵循统一的数据格式：

```python
fund = {
    "symbol": "000017",
    "basic_info": {
        "ok": True,
        "data": [
            {"item": "字段名", "value": "字段值"},
            ...
        ]
    },
    "achievement": {
        "ok": True,
        "data": [
            {"item": "指标名", "value": "指标值"},
            ...
        ]
    }
}
```

## 测试覆盖

新增测试文件 `tests/test_fund_formatter_enhanced.py`，包含：

1. `test_format_basic_info_table` - 测试基本信息表格生成
2. `test_format_return_bar_chart` - 测试收益率柱状图生成
3. `test_format_fee_donut_chart` - 测试费率环形图生成
4. `test_format_risk_indicator_chart` - 测试风险指标柱状图生成
5. `test_build_compare_output_enhanced` - 测试完整的对比输出

所有测试均已通过。

## 使用示例

```python
from backend.pkg.fund_formatter import build_compare_output

# 准备数据
supplier_data = {
    "payload": {
        "funds": [
            # 基金1数据
            {...},
            # 基金2数据
            {...}
        ]
    }
}

llm_text = "【综合评价】\n..."

# 生成对比报告
result = build_compare_output(supplier_data, llm_text)

# 结果包含
# - result["charts"]: 6种图表
# - result["sections"]: 3个表格 + LLM文本sections
# - result["cards"]: 基金信息卡片
```

## 前端适配建议

前端需要支持以下图表类型的渲染：

1. **bar** (柱状图) - 用于收益率和风险指标对比
2. **donut** (环形图) - 用于费率结构展示
3. **line** (折线图) - 用于净值走势
4. **radar** (雷达图) - 用于投资风格对比
5. **pie** (饼图) - 用于资产配置

## 后续优化建议

1. 支持更多时间维度的收益率对比（如近2年、近5年）
2. 增加行业配置对比图表
3. 增加持仓重叠度分析
4. 支持自定义图表显示顺序
5. 支持导出为PDF或图片格式

## 版本信息

- 修改文件: `backend/pkg/fund_formatter.py`
- 测试文件: `tests/test_fund_formatter_enhanced.py`
- 修改日期: 2025-01-XX
- 修改人: AI Assistant
