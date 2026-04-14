# 修复基金对比图表为空的问题

## 问题描述

在基金对比功能中，前端收到的 `structuredOutputs` 中 `charts` 字段为空数组 `[]`，导致图表无法显示。

从浏览器控制台调试输出：
```javascript
charts: 0 []  // ❌ 图表数组为空
sections: 5   // ✅ sections 正常
cards: 2      // ✅ cards 正常
```

## 根本原因

在 `backend/agents/fund_agent/product_compare/agent.py` 的 `run` 方法中（第 191-193 行），构建 `supplier_data` 时数据格式不正确：

```python
# ❌ 错误的构建方式
supplier_data = {
    "ok": True,
    "symbols": [fund.get("symbol") for fund in valid_funds],
    "funds": [fund.get("data", {}) for fund in valid_funds],  # 缺少 symbol 字段
}
```

问题：
1. `fund.get("data", {})` 提取的数据缺少 `symbol` 字段
2. 图表生成函数（如 `format_nav_chart`、`format_return_bar_chart` 等）依赖 `fund["symbol"]` 来标识系列名称
3. 没有 `symbol` 时，图表生成函数返回 `None`，导致 `charts` 数组为空

## 数据流分析

### AkShareClient 返回格式
```python
[
    {
        "symbol": "000032",
        "ok": True,
        "data": {
            "basic_info": {...},
            "achievement": {...},
            ...
        }
    },
    ...
]
```

### fund_formatter 期望格式
```python
{
    "payload": {
        "funds": [
            {
                "symbol": "000032",  # ✅ 必须包含 symbol
                "basic_info": {...},
                "achievement": {...},
                ...
            },
            ...
        ]
    }
}
```

## 修复方案

修改 `backend/agents/fund_agent/product_compare/agent.py` 第 185-200 行：

```python
# ✅ 正确的构建方式
# 构建 supplier_data（兼容 fund_formatter 接口）
# 需要将 AkShare 返回的格式转换为 fund_formatter 期望的格式
funds_for_formatter = []
for fund in valid_funds:
    fund_data = fund.get("data", {})
    fund_data["symbol"] = fund.get("symbol")  # ✅ 添加 symbol 字段
    funds_for_formatter.append(fund_data)

supplier_data = {
    "payload": {
        "funds": funds_for_formatter
    }
}

# 生成结构化输出
structured_output = build_compare_output(supplier_data, llm_text)
```

## 测试验证

### 测试脚本
创建了 `backend/test_akshare_format.py` 来验证修复效果。

### 测试结果
```
图表数量: 3  ✅
卡片数量: 6  ✅
Sections 数量: 4  ✅

图表列表:
  - [line] 各期收益对比
      系列: 000032, 数据点: 6
      系列: 000037, 数据点: 6
  - [bar] 各期收益率对比
      系列: 000032, 数据点: 4
      系列: 000037, 数据点: 4
  - [donut] 000032 费率结构
```

## 影响范围

- 文件：`backend/agents/fund_agent/product_compare/agent.py`
- 方法：`ProductCompareAgent.run()`
- 影响：基金对比功能的图表显示

## 相关文件

- `backend/pkg/fund_formatter.py` - 图表生成逻辑
- `backend/agents/fund_agent/product_compare/agent.py` - 对比 Agent
- `backend/test_akshare_format.py` - 测试脚本
- `backend/test_compare_fix.py` - 对比测试脚本

## 后续建议

1. 添加单元测试覆盖数据格式转换逻辑
2. 在 `build_compare_output` 中添加数据验证，当 `symbol` 缺失时给出明确警告
3. 考虑在 `fund_formatter.py` 中添加更健壮的错误处理

## 验证步骤

1. 重启后端服务
2. 在前端输入："000032和000037的对比"
3. 检查返回的 `structuredOutputs.charts` 是否包含图表数据
4. 验证图表是否正常渲染

## 时间线

- 2024-XX-XX: 发现问题（charts 为空）
- 2024-XX-XX: 定位根本原因（缺少 symbol 字段）
- 2024-XX-XX: 实施修复并测试验证
