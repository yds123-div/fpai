# AkShare 基金数据可用性分析

## 文档信息

- **创建日期**：2026-04-10
- **AkShare 版本**：1.18.54
- **测试基金代码**：000001（华夏成长混合）

---

## 数据可用性总结

### ✅ 完全可用的数据

| 数据类型 | AkShare 接口 | 数据源 | 说明 |
|---------|-------------|--------|------|
| **资产配置** | `fund_individual_detail_hold_xq` | 雪球 | ✅ 股票、债券、现金、其他占比 |
| **净值走势** | `fund_open_fund_info_em` | 东方财富 | ✅ 逐日单位净值和日增长率 |
| **行业配置** | `fund_portfolio_industry_allocation_em` | 东方财富 | ✅ 各行业占净值比例 |
| **持仓明细** | `fund_portfolio_hold_em` | 东方财富 | ✅ 具体持仓股票及占比 |
| **业绩表现** | `fund_individual_achievement_xq` | 雪球 | ✅ 各时间段收益率和回撤 |
| **基本信息** | `fund_individual_basic_info_xq` | 雪球 | ✅ 基金代码、名称、规模等 |
| **费率信息** | `fund_individual_detail_info_xq` | 雪球 | ✅ 申购费、赎回费、管理费等 |
| **风险指标** | `fund_individual_analysis_xq` | 雪球 | ✅ 波动率、夏普比率、最大回撤 |

---

## 详细数据结构

### 1. 资产配置数据

**接口**：`fund_individual_detail_hold_xq(symbol='000001')`

**数据源**：雪球

**返回结构**：
```python
{
    "ok": True,
    "data": [
        {"资产类型": "股票", "仓位占比": 67.37},
        {"资产类型": "债券", "仓位占比": 20.93},
        {"资产类型": "现金", "仓位占比": 10.02},
        {"资产类型": "其他", "仓位占比": 3.98}
    ]
}
```

**可用于**：
- ✅ 环形图（资产配置饼图）
- ✅ 柱状图（资产配置对比）

**示例代码**：
```python
import akshare as ak

df = ak.fund_individual_detail_hold_xq(symbol='000001')
print(df)
#   资产类型   仓位占比
# 0   股票  67.37
# 1   债券  20.93
# 2   现金  10.02
# 3   其他   3.98
```

---

### 2. 净值走势数据

**接口**：`fund_open_fund_info_em(symbol='000001', indicator='单位净值走势', period='1年')`

**数据源**：东方财富

**返回结构**：
```python
{
    "净值日期": ["2023-04-10", "2023-04-11", ...],
    "单位净值": [1.020, 1.025, ...],
    "日增长率": [0.49, 0.49, ...]
}
```

**数据量**：
- 成立来：5898 条记录（2001-12-18 至今）
- 1年：约 250 条记录
- 3年：约 750 条记录

**可用于**：
- ✅ 折线图（净值走势）
- ✅ 折线图（累计收益率走势）
- ✅ 对比图（多只基金净值对比）

**示例代码**：
```python
import akshare as ak

# 获取近1年净值走势
df = ak.fund_open_fund_info_em(
    symbol='000001', 
    indicator='单位净值走势', 
    period='1年'
)

print(df.head())
#          净值日期   单位净值    日增长率
# 0  2023-04-10  1.020  0.49
# 1  2023-04-11  1.025  0.49
# ...

# 可选的 period 参数
# "1月", "3月", "6月", "1年", "3年", "5年", "今年来", "成立来"
```

**累计收益率计算**：
```python
# 方法1：使用日增长率累乘
df['累计收益率'] = (1 + df['日增长率'] / 100).cumprod() - 1

# 方法2：使用单位净值计算
df['累计收益率'] = (df['单位净值'] / df['单位净值'].iloc[0] - 1) * 100
```

---

### 3. 行业配置数据

**接口**：`fund_portfolio_industry_allocation_em(symbol='000001', date='2023')`

**数据源**：东方财富

**返回结构**：
```python
{
    "序号": [1, 2, 3, ...],
    "行业类别": ["制造业", "信息传输、软件和信息技术服务业", ...],
    "占净值比例": [56.58, 5.72, ...],
    "市值": [136966.39, 13849.95, ...],
    "截止时间": ["2023-12-31", "2023-12-31", ...]
}
```

**可用于**：
- ✅ 柱状图（行业配置）
- ✅ 环形图（行业占比）

**示例代码**：
```python
import akshare as ak

df = ak.fund_portfolio_industry_allocation_em(symbol='000001', date='2023')
print(df.head())
#    序号             行业类别  占净值比例             市值        截止时间
# 0    1              制造业  56.58  136966.393202  2023-12-31
# 1    2  信息传输、软件和信息技术服务业   5.72   13849.954346  2023-12-31
```

---

### 4. 持仓明细数据

**接口**：`fund_portfolio_hold_em(symbol='000001', date='2023')`

**数据源**：东方财富

**返回结构**：
```python
{
    "序号": [1, 2, 3, ...],
    "股票代码": ["300395", "300593", ...],
    "股票名称": ["菲利华", "新雷能", ...],
    "占净值比例": [8.03, 7.01, ...],
    "持股数": [536.81, 653.62, ...],
    "持仓市值": [23565.83, 20562.93, ...],
    "季度": ["2023年1季度股票投资明细", ...]
}
```

**可用于**：
- ✅ 表格（前十大重仓股）
- ✅ 柱状图（持仓占比）

**示例代码**：
```python
import akshare as ak

df = ak.fund_portfolio_hold_em(symbol='000001', date='2023')
print(df.head())
#    序号    股票代码  股票名称  占净值比例     持股数      持仓市值              季度
# 0    1  300395   菲利华   8.03  536.81  23565.83  2023年1季度股票投资明细
```

---

### 5. 业绩表现数据

**接口**：`fund_individual_achievement_xq(symbol='000001')`

**数据源**：雪球

**返回结构**：
```python
{
    "业绩类型": ["年度业绩", "年度业绩", "阶段业绩", ...],
    "周期": ["成立以来", "今年以来", "近1月", ...],
    "本产品区间收益": [600.44, -0.55, -1.64, ...],
    "本产品最大回撒": [59.09, 15.89, NaN, ...],
    "周期收益同类排名": ["102/5283", "3681/5283", ...]
}
```

**可用于**：
- ✅ 表格（业绩对比）
- ✅ 柱状图（收益率对比）
- ✅ 折线图（历史年度收益）

**示例代码**：
```python
import akshare as ak

df = ak.fund_individual_achievement_xq(symbol='000001')
print(df.head())
#    业绩类型    周期     本产品区间收益  本产品最大回撒   周期收益同类排名
# 0  年度业绩  成立以来  600.442000    59.09   102/5283
# 1  年度业绩  今年以来   -0.554019    15.89  3681/5283
```

---

### 6. 基本信息数据

**接口**：`fund_individual_basic_info_xq(symbol='000001')`

**数据源**：雪球

**返回结构**：
```python
{
    "item": ["基金代码", "基金名称", "基金全称", "成立时间", "最新规模", ...],
    "value": ["000001", "华夏成长混合", "华夏成长证券投资基金", "2001-12-18", "29.37亿", ...]
}
```

**可用于**：
- ✅ 卡片（基本信息展示）

**示例代码**：
```python
import akshare as ak

df = ak.fund_individual_basic_info_xq(symbol='000001')
print(df.head())
#   item       value
# 0  基金代码      000001
# 1  基金名称      华夏成长混合
# 2  基金全称  华夏成长证券投资基金
# 3  成立时间  2001-12-18
# 4  最新规模      29.37亿
```

---

### 7. 费率信息数据

**接口**：`fund_individual_detail_info_xq(symbol='000001')`

**数据源**：雪球

**返回结构**：
```python
{
    "费用类型": ["买入规则", "买入规则", "卖出规则", "其他费用", ...],
    "条件或名称": ["0.0万<买入金额<100.0万", "7.0天<=持有期限", "基金管理费", ...],
    "费用": [1.5, 0.5, 1.2, ...]
}
```

**可用于**：
- ✅ 卡片（费率信息展示）
- ✅ 表格（费率对比）

**示例代码**：
```python
import akshare as ak

df = ak.fund_individual_detail_info_xq(symbol='000001')
print(df.head())
#   费用类型                 条件或名称      费用
# 0  买入规则      0.0万<买入金额<100.0万     1.5
# 1  买入规则   100.0万<=买入金额<500.0万     1.2
# 2  卖出规则        0.0天<持有期限<7.0天     1.5
# 3  卖出规则            7.0天<=持有期限     0.5
# 4  其他费用                 基金管理费     1.2
```

---

### 8. 风险指标数据

**接口**：`fund_individual_analysis_xq(symbol='000001')`

**数据源**：雪球

**返回结构**：
```python
{
    "周期": ["近1年", "近3年", "近5年"],
    "较同类风险收益比": [35, 53, 29],
    "较同类抗风险波动": [38, 62, 55],
    "年化波动率": [22.96, 20.48, 19.88],
    "年化夏普比率": [1.42, 0.15, -0.22],
    "最大回撤": [15.89, 30.57, 53.15]
}
```

**可用于**：
- ✅ 卡片（风险指标展示）
- ✅ 雷达图（风险收益特征）
- ✅ 表格（风险指标对比）

**示例代码**：
```python
import akshare as ak

df = ak.fund_individual_analysis_xq(symbol='000001')
print(df)
#     周期  较同类风险收益比  较同类抗风险波动  年化波动率  年化夏普比率   最大回撤
# 0  近1年        35        38  22.96    1.42  15.89
# 1  近3年        53        62  20.48    0.15  30.57
# 2  近5年        29        55  19.88   -0.22  53.15
```

---

## 数据转换建议

### 1. 资产配置 → 环形图

```python
def format_asset_chart(fund_data: dict) -> dict:
    """将资产配置数据转换为环形图配置"""
    df = fund_data.get("detail_hold", {}).get("data", [])
    
    return {
        "id": f"asset_{fund_data['symbol']}",
        "title": "资产配置",
        "type": "pie",
        "data": {
            "labels": [row["资产类型"] for row in df],
            "values": [row["仓位占比"] for row in df],
            "colors": ["#5470c6", "#91cc75", "#fac858", "#ee6666"]
        },
        "options": {
            "showPercentage": True,
            "innerRadius": "50%"
        }
    }
```

### 2. 净值走势 → 折线图

```python
def format_nav_chart(fund_data: dict, period: str = "1年") -> dict:
    """将净值走势数据转换为折线图配置"""
    import akshare as ak
    
    symbol = fund_data["symbol"]
    df = ak.fund_open_fund_info_em(
        symbol=symbol, 
        indicator="单位净值走势", 
        period=period
    )
    
    # 计算累计收益率
    df["累计收益率"] = (df["单位净值"] / df["单位净值"].iloc[0] - 1) * 100
    
    return {
        "id": f"nav_{symbol}",
        "title": "净值走势",
        "type": "line",
        "description": f"近{period}",
        "data": {
            "xAxis": df["净值日期"].tolist(),
            "series": [
                {
                    "name": "累计收益率",
                    "data": df["累计收益率"].tolist(),
                    "color": "#5470c6"
                }
            ]
        },
        "options": {
            "showLegend": True,
            "showGrid": True,
            "yAxisLabel": "累计收益率(%)"
        }
    }
```

### 3. 业绩表现 → 对比表格

```python
def format_performance_table(funds: list[dict]) -> dict:
    """将业绩表现数据转换为对比表格"""
    
    # 提取各时间段收益率
    periods = ["近1月", "近3月", "近6月", "近1年", "近3年"]
    
    rows = []
    for period in periods:
        row = {"时间段": period}
        for fund in funds:
            achievement = fund.get("achievement", {}).get("data", [])
            for item in achievement:
                if item["周期"] == period:
                    row[fund["symbol"]] = f"{item['本产品区间收益']:.2f}%"
                    break
        rows.append(row)
    
    return {
        "id": "performance_compare",
        "title": "业绩对比",
        "type": "table",
        "table": {
            "headers": ["时间段"] + [f["symbol"] for f in funds],
            "rows": rows,
            "highlight": [f["symbol"] for f in funds]
        }
    }
```

---

## 数据限制与注意事项

### 1. 数据源稳定性

| 数据源 | 稳定性 | 说明 |
|--------|--------|------|
| 雪球 | ⚠️ 中等 | 可能有反爬限制，建议添加重试机制 |
| 东方财富 | ✅ 较好 | 数据较稳定，但需注意请求频率 |

### 2. 数据更新频率

- **净值数据**：每日更新（交易日）
- **持仓数据**：季度更新（季报披露后）
- **资产配置**：季度更新
- **业绩数据**：实时更新

### 3. 数据缺失处理

```python
def safe_get_fund_data(symbol: str, func_name: str, **kwargs):
    """安全获取基金数据，处理异常"""
    try:
        import akshare as ak
        func = getattr(ak, func_name)
        df = func(symbol=symbol, **kwargs)
        return {"ok": True, "data": df.to_dict(orient="records")}
    except Exception as e:
        return {"ok": False, "message": str(e), "data": []}
```

### 4. 性能优化建议

- **缓存**：对于不常变化的数据（如持仓、行业配置），建议缓存
- **并发**：使用异步请求提高数据获取速度
- **限流**：添加请求间隔，避免被封IP

---

## 实施建议

### 阶段 1：核心数据（优先级高）

1. ✅ 资产配置（环形图）
2. ✅ 净值走势（折线图）
3. ✅ 业绩表现（对比表格）
4. ✅ 基本信息（卡片）

### 阶段 2：扩展数据（优先级中）

5. ✅ 行业配置（柱状图）
6. ✅ 持仓明细（表格）
7. ✅ 费率信息（卡片）
8. ✅ 风险指标（雷达图）

### 阶段 3：高级功能（优先级低）

9. ⏳ 基金对比（多只基金净值走势对比）
10. ⏳ 历史回测（不同时间段买入的收益模拟）
11. ⏳ 风险分析（波动率、夏普比率趋势）

---

## 相关文件

- [多模态输出设计文档](./multimodal_output_design.md)
- [实施计划](./multimodal_implementation_plan.md)
- [测试脚本](../tests/test_akshare_fund_data.py)
- [净值数据测试](../tests/test_akshare_nav_data.py)

---

**最后更新**：2026-04-10
