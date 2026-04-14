# 基金14字段标准输出功能

## 概述

已在 `backend/pkg/fund_formatter.py` 中集成14字段标准信息表格输出功能，会在基金解读和对比时自动展示。

## 14个标准字段

根据业务需求，标准输出包含以下14个字段：

1. **基金代码** - 6位数字代码（如：000029）
2. **基金名称** - 基金简称（如：富国宏观策略灵活配置混合A）
3. **基金全称** - 完整的基金名称（如：富国宏观策略灵活配置混合型证券投资基金）
4. **成立时间** - 基金成立日期（如：2013-04-12）
5. **最新规模** - 基金资产净值（如：2.08亿）
6. **基金公司** - 基金管理人（如：富国基金管理有限公司）
7. **基金经理** - 当前基金经理姓名（如：袁宜）
8. **托管银行** - 基金托管银行（如：中国建设银行股份有限公司）
9. **基金类型** - 基金分类（如：混合型-宏观策略）
10. **评级机构** - 评级公司名称（如：null 表示无评级机构）
11. **基金评级** - 评级结果（如：暂无评级）
12. **投资策略** - 投资策略描述（如：自上而下与自下而上相结合...）
13. **投资目标** - 投资目标描述（如：通过灵活合理的大类资产配置...）
14. **业绩比较基准** - 业绩比较基准（如：沪深300指数收益率×65%+中债综合指数收益率×35%）

## 集成位置

### 1. 单基金解读（ProductInterpretAgent）

在 `build_single_output` 函数中，会自动为每只基金生成14字段表格，输出在 `sections` 中。

**调用链路**：
```
ProductInterpretAgent.run()
  → build_single_output(supplier_data, llm_text)
    → format_standard_14_fields_table(fund)  # 为每只基金生成14字段表格
```

**输出位置**：
- 表格会出现在 `FundAnalysisOutput.sections` 数组的开头
- 在 LLM 生成的文本段落之前展示

### 2. 基金对比（ProductCompareAgent）

在 `build_compare_output` 函数中，会为每只基金生成独立的14字段表格，然后再展示对比表格。

**调用链路**：
```
ProductCompareAgent.run()
  → build_compare_output(supplier_data, llm_text)
    → format_standard_14_fields_table(fund)  # 为每只基金生成14字段表格
    → format_basic_info_table(funds)         # 生成对比表格
```

**输出顺序**：
1. 每只基金的14字段标准信息表格
2. 基金对比表格（基本信息、业绩、费率）
3. LLM 生成的文本段落

## 函数实现

### format_standard_14_fields_table

```python
def format_standard_14_fields_table(fund_obj: dict[str, Any]) -> TableSection | None:
    """格式化基金标准14字段信息表格。
    
    Args:
        fund_obj: 基金数据对象，包含 symbol 和 basic_info/detail_info 等模块
        
    Returns:
        TableSection 或 None（如果数据不足）
    """
```

**字段映射逻辑**：
- 函数会自动尝试从多个可能的源字段名称中提取数据
- 例如："基金名称" 会尝试匹配 ["基金名称", "基金简称", "名称"]
- 如果某个字段在数据源中不存在，会显示 "-"

## 输出数据结构

```python
{
    "id": "standard_14_fields_000029",
    "title": "基本信息（14个字段）",
    "type": "table",
    "table": {
        "headers": ["字段", "内容"],
        "rows": [
            {"字段": "基金代码", "内容": "000029"},
            {"字段": "基金名称", "内容": "富国宏观策略灵活配置混合A"},
            {"字段": "基金全称", "内容": "富国宏观策略灵活配置混合型证券投资基金"},
            {"字段": "成立时间", "内容": "2013-04-12"},
            {"字段": "最新规模", "内容": "2.08亿"},
            {"字段": "基金公司", "内容": "富国基金管理有限公司"},
            {"字段": "基金经理", "内容": "袁宜"},
            {"字段": "托管银行", "内容": "中国建设银行股份有限公司"},
            {"字段": "基金类型", "内容": "混合型-宏观策略"},
            {"字段": "评级机构", "内容": "null"},
            {"字段": "基金评级", "内容": "暂无评级"},
            {"字段": "投资策略", "内容": "自上而下与自下而上相结合..."},
            {"字段": "投资目标", "内容": "通过灵活合理的大类资产配置..."},
            {"字段": "业绩比较基准", "内容": "沪深300指数收益率×65%+中债综合指数收益率×35%"}
        ]
    }
}
```

## 前端展示

前端会接收到包含14字段表格的 `FundAnalysisOutput`：

```typescript
interface FundAnalysisOutput {
  type: "fund_analysis";
  mode: "single" | "compare";
  summary: string;
  cards: InfoCard[];
  sections: (TextSection | TableSection)[];  // 14字段表格在这里
  charts: ChartConfig[];
  text: string;
}
```

前端可以根据 `section.type === "table"` 来识别表格，并渲染为表格组件。

## 使用示例

### 查询单只基金

用户输入：
```
帮我分析一下 000029
```

Agent 返回的 JSON 中会包含：
```json
{
  "type": "fund_analysis",
  "mode": "single",
  "sections": [
    {
      "id": "standard_14_fields_000029",
      "title": "基本信息（14个字段）",
      "type": "table",
      "table": {
        "headers": ["字段", "内容"],
        "rows": [...]
      }
    },
    {
      "type": "text",
      "content": "该基金是一只混合型基金..."
    }
  ]
}
```

### 对比多只基金

用户输入：
```
对比 000029 和 110022
```

Agent 返回的 JSON 中会包含：
```json
{
  "type": "fund_analysis",
  "mode": "compare",
  "sections": [
    {
      "id": "standard_14_fields_000029",
      "title": "基本信息（14个字段）",
      "type": "table",
      "table": {...}
    },
    {
      "id": "standard_14_fields_110022",
      "title": "基本信息（14个字段）",
      "type": "table",
      "table": {...}
    },
    {
      "id": "basic_info_compare",
      "title": "基本信息对比",
      "type": "table",
      "table": {...}
    }
  ]
}
```

## 注意事项

1. **自动集成**：功能已自动集成到 `build_single_output` 和 `build_compare_output`，无需额外调用
2. **数据来源**：从 AkShare 的 `basic_info` 或 `detail_info` 模块提取数据
3. **字段缺失**：如果某些字段在数据源中不存在，会显示 "-"
4. **表格顺序**：14字段表格会出现在 sections 数组的开头，在文本段落之前

## 相关文件

- **实现**: `backend/pkg/fund_formatter.py`
  - `format_standard_14_fields_table()` - 生成14字段表格
  - `build_single_output()` - 单基金解读输出（已集成）
  - `build_compare_output()` - 基金对比输出（已集成）
- **调用方**:
  - `backend/agents/fund_agent/product_interpret/agent.py` - 单基金解读 Agent
  - `backend/agents/fund_agent/product_compare/agent.py` - 基金对比 Agent

## 验证方法

可以通过以下方式验证功能：

1. **启动后端服务**
2. **发送基金查询请求**（通过 API 或聊天界面）
3. **检查返回的 JSON**，确认 `sections` 中包含14字段表格
4. **前端渲染**，确认表格正确显示

示例 API 请求：
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "帮我分析一下 000029"}'
```

返回的 JSON 中应该包含14字段表格。
