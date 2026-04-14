# 基金分析多模态输出方案

## 背景

当前基金分析输出纯文本，用户需要从大段文字中提取关键信息。改进方案：输出结构化数据，前端渲染为表格、图表、卡片等多模态形式。

## 设计原则

1. **表格化**：关键指标用对比表格呈现，一目了然
2. **图形化**：资产配置用环形图，净值走势用折线图
3. **模块化**：使用明显的色块和标题区分不同功能区
4. **置顶卡片**：基础信息、费率、核心表现指标抽离成卡片

## 输出格式设计

### 方案 A：纯结构化 JSON（推荐）

Agent 输出 JSON，包含文本 + 结构化数据：

```json
{
  "type": "fund_analysis",
  "mode": "single|compare",
  "summary": "简短总结（1-2句）",
  "cards": [...],      // 置顶卡片
  "sections": [...],   // 各个分析模块
  "charts": [...],     // 图表配置
  "text": "完整文本（兜底）"
}
```

### 方案 B：Markdown + 特殊标记

在 Markdown 中嵌入特殊标记，前端解析：

```markdown
【基本信息卡片】
:::card
{json数据}
:::

【业绩对比表格】
:::table
{json数据}
:::
```

## 详细方案（方案 A）


### 1. 输出结构

```typescript
interface FundAnalysisOutput {
  type: "fund_analysis";
  mode: "single" | "compare";
  summary: string;
  cards: InfoCard[];
  sections: AnalysisSection[];
  charts: ChartConfig[];
  text: string;  // 完整文本（兜底）
}
```

### 2. 置顶卡片（InfoCard）

```typescript
interface InfoCard {
  id: string;
  title: string;
  type: "basic" | "performance" | "risk" | "fee";
  data: Record<string, any>;
}
```

**示例**：

```json
{
  "cards": [
    {
      "id": "basic_000044",
      "title": "基本信息",
      "type": "basic",
      "data": {
        "code": "000044",
        "name": "嘉实美国成长股票(QDII)",
        "type": "QDII",
        "manager": "张自力",
        "scale": "12.5亿",
        "riskLevel": "R3-中风险",
        "status": "开放申购赎回"
      }
    },
    {
      "id": "performance_000044",
      "title": "核心表现",
      "type": "performance",
      "data": {
        "return_1y": "15.23%",
        "return_3y": "45.67%",
        "sharpe": "1.25",
        "maxDrawdown": "-12.34%"
      }
    }
  ]
}
```


### 3. 对比表格（AnalysisSection - Table）

```typescript
interface TableSection {
  id: string;
  title: string;
  type: "table";
  description?: string;
  table: {
    headers: string[];
    rows: Array<Record<string, any>>;
    highlight?: string[];  // 高亮列
  };
}
```

**示例**：

```json
{
  "sections": [
    {
      "id": "compare_risk_return",
      "title": "风险收益对比",
      "type": "table",
      "description": "近3年数据对比",
      "table": {
        "headers": ["指标", "000044", "000042", "同类平均"],
        "rows": [
          {"指标": "年化收益", "000044": "15.23%", "000042": "12.45%", "同类平均": "10.50%"},
          {"指标": "最大回撤", "000044": "-12.34%", "000042": "-15.67%", "同类平均": "-18.20%"},
          {"指标": "夏普比率", "000044": "1.25", "000042": "0.98", "同类平均": "0.85"},
          {"指标": "波动率", "000044": "18.5%", "000042": "22.3%", "同类平均": "25.1%"}
        ],
        "highlight": ["000044", "000042"]
      }
    }
  ]
}
```


### 4. 图表配置（ChartConfig）

```typescript
interface ChartConfig {
  id: string;
  title: string;
  type: "pie" | "line" | "bar" | "radar";
  description?: string;
  data: any;
  options?: any;
}
```

#### 4.1 环形图（资产配置）

```json
{
  "charts": [
    {
      "id": "asset_allocation_000044",
      "title": "资产配置",
      "type": "pie",
      "description": "截至 2023-12-31",
      "data": {
        "labels": ["股票", "债券", "现金", "其他"],
        "values": [85.5, 8.2, 4.3, 2.0],
        "colors": ["#5470c6", "#91cc75", "#fac858", "#ee6666"]
      },
      "options": {
        "showPercentage": true,
        "innerRadius": "50%"
      }
    }
  ]
}
```

#### 4.2 折线图（净值走势）

```json
{
  "id": "nav_trend",
  "title": "净值走势对比",
  "type": "line",
  "description": "近1年",
  "data": {
    "xAxis": ["2023-04", "2023-05", "2023-06", "...", "2024-04"],
    "series": [
      {
        "name": "000044",
        "data": [1.0, 1.05, 1.08, "...", 1.15],
        "color": "#5470c6"
      },
      {
        "name": "000042",
        "data": [1.0, 1.03, 1.06, "...", 1.12],
        "color": "#91cc75"
      },
      {
        "name": "同类平均",
        "data": [1.0, 1.02, 1.04, "...", 1.10],
        "color": "#fac858",
        "style": "dashed"
      }
    ]
  },
  "options": {
    "showLegend": true,
    "showGrid": true,
    "yAxisLabel": "累计收益率"
  }
}
```


#### 4.3 雷达图（风格分析）

```json
{
  "id": "style_radar",
  "title": "投资风格对比",
  "type": "radar",
  "data": {
    "indicators": [
      {"name": "成长性", "max": 100},
      {"name": "价值性", "max": 100},
      {"name": "大盘", "max": 100},
      {"name": "中盘", "max": 100},
      {"name": "小盘", "max": 100}
    ],
    "series": [
      {
        "name": "000044",
        "data": [85, 30, 70, 20, 10],
        "color": "#5470c6"
      },
      {
        "name": "000042",
        "data": [60, 50, 50, 40, 10],
        "color": "#91cc75"
      }
    ]
  }
}
```

### 5. 文本模块（AnalysisSection - Text）

```typescript
interface TextSection {
  id: string;
  title: string;
  type: "text";
  content: string;
  tags?: string[];  // 标签：如 "风险提示"
}
```

**示例**：

```json
{
  "id": "conclusion",
  "title": "分析结论",
  "type": "text",
  "content": "000044 是一只成长风格的 QDII 基金...",
  "tags": ["专家观点"]
}
```


## 完整示例

### 单只基金解读

```json
{
  "type": "fund_analysis",
  "mode": "single",
  "summary": "000044 是一只成长风格的 QDII 基金，近3年表现优异，适合风险承受能力较高的投资者。",
  
  "cards": [
    {
      "id": "basic",
      "title": "基本信息",
      "type": "basic",
      "data": {
        "code": "000044",
        "name": "嘉实美国成长股票(QDII)",
        "type": "QDII",
        "manager": "张自力 (任职5年)",
        "scale": "12.5亿",
        "riskLevel": "R3-中风险",
        "status": "开放申购赎回"
      }
    },
    {
      "id": "fee",
      "title": "费率信息",
      "type": "fee",
      "data": {
        "managementFee": "1.50%",
        "custodyFee": "0.25%",
        "subscriptionFee": "1.20% (打1折后 0.12%)",
        "redemptionFee": "持有<7天: 1.5%, ≥2年: 0%"
      }
    },
    {
      "id": "performance",
      "title": "核心表现",
      "type": "performance",
      "data": {
        "return_1y": "+15.23%",
        "return_3y": "+45.67%",
        "sharpe": "1.25",
        "maxDrawdown": "-12.34%",
        "volatility": "18.5%"
      }
    }
  ],
  
  "sections": [
    {
      "id": "performance_detail",
      "title": "业绩表现",
      "type": "table",
      "description": "各时间段收益对比",
      "table": {
        "headers": ["时间段", "本基金", "业绩基准", "同类平均", "沪深300"],
        "rows": [
          {"时间段": "近1月", "本基金": "+2.5%", "业绩基准": "+2.1%", "同类平均": "+1.8%", "沪深300": "+1.5%"},
          {"时间段": "近3月", "本基金": "+8.3%", "业绩基准": "+7.5%", "同类平均": "+6.2%", "沪深300": "+5.8%"},
          {"时间段": "近1年", "本基金": "+15.2%", "业绩基准": "+13.8%", "同类平均": "+10.5%", "沪深300": "+8.9%"},
          {"时间段": "近3年", "本基金": "+45.7%", "业绩基准": "+40.2%", "同类平均": "+32.1%", "沪深300": "+25.3%"}
        ],
        "highlight": ["本基金"]
      }
    },
    {
      "id": "conclusion",
      "title": "分析结论",
      "type": "text",
      "content": "该基金长期表现优异，持续跑赢业绩基准和同类平均。基金经理张自力任职期间年化回报达 15.2%，展现出较强的选股能力。适合风险承受能力较高、看好美股成长板块的投资者长期持有。",
      "tags": ["专家观点"]
    },
    {
      "id": "risk_warning",
      "title": "风险提示",
      "type": "text",
      "content": "基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议。",
      "tags": ["风险提示"]
    }
  ],
  
  "charts": [
    {
      "id": "asset_allocation",
      "title": "资产配置",
      "type": "pie",
      "description": "截至 2023-12-31",
      "data": {
        "labels": ["股票", "债券", "现金", "其他"],
        "values": [85.5, 8.2, 4.3, 2.0],
        "colors": ["#5470c6", "#91cc75", "#fac858", "#ee6666"]
      }
    },
    {
      "id": "nav_trend",
      "title": "净值走势",
      "type": "line",
      "description": "近1年累计收益率",
      "data": {
        "xAxis": ["2023-04", "2023-05", "2023-06", "2023-07", "2023-08", "2023-09", "2023-10", "2023-11", "2023-12", "2024-01", "2024-02", "2024-03", "2024-04"],
        "series": [
          {
            "name": "本基金",
            "data": [0, 2.5, 5.1, 7.8, 6.5, 8.9, 10.2, 11.5, 12.8, 13.2, 14.1, 14.8, 15.2],
            "color": "#5470c6"
          },
          {
            "name": "业绩基准",
            "data": [0, 2.1, 4.5, 6.8, 5.9, 7.8, 9.1, 10.2, 11.3, 11.8, 12.5, 13.1, 13.8],
            "color": "#91cc75",
            "style": "dashed"
          },
          {
            "name": "同类平均",
            "data": [0, 1.8, 3.9, 5.5, 4.8, 6.2, 7.1, 8.0, 8.9, 9.2, 9.8, 10.2, 10.5],
            "color": "#fac858",
            "style": "dashed"
          }
        ]
      }
    }
  ],
  
  "text": "【基本信息】\n000044 嘉实美国成长股票(QDII)，QDII 型基金..."
}
```


### 基金对比

```json
{
  "type": "fund_analysis",
  "mode": "compare",
  "summary": "000044 和 000042 均为 QDII 基金，000044 成长风格更明显，近3年收益更高但波动也更大。",
  
  "cards": [
    {
      "id": "compare_basic",
      "title": "基本信息对比",
      "type": "basic",
      "data": {
        "funds": [
          {
            "code": "000044",
            "name": "嘉实美国成长",
            "type": "QDII",
            "manager": "张自力",
            "scale": "12.5亿",
            "riskLevel": "R3"
          },
          {
            "code": "000042",
            "name": "财通纯债",
            "type": "债券型",
            "manager": "李明",
            "scale": "8.3亿",
            "riskLevel": "R2"
          }
        ]
      }
    }
  ],
  
  "sections": [
    {
      "id": "compare_performance",
      "title": "业绩对比",
      "type": "table",
      "table": {
        "headers": ["指标", "000044", "000042", "差异"],
        "rows": [
          {"指标": "近1年收益", "000044": "+15.23%", "000042": "+12.45%", "差异": "+2.78%"},
          {"指标": "近3年收益", "000044": "+45.67%", "000042": "+38.92%", "差异": "+6.75%"},
          {"指标": "最大回撤", "000044": "-12.34%", "000042": "-15.67%", "差异": "+3.33%"},
          {"指标": "夏普比率", "000044": "1.25", "000042": "0.98", "差异": "+0.27"},
          {"指标": "波动率", "000044": "18.5%", "000042": "22.3%", "差异": "-3.8%"}
        ],
        "highlight": ["000044", "000042"]
      }
    },
    {
      "id": "compare_fee",
      "title": "费率对比",
      "type": "table",
      "table": {
        "headers": ["费用类型", "000044", "000042"],
        "rows": [
          {"费用类型": "管理费", "000044": "1.50%", "000042": "0.70%"},
          {"费用类型": "托管费", "000044": "0.25%", "000042": "0.20%"},
          {"费用类型": "申购费", "000044": "0.12% (打折后)", "000042": "0.08% (打折后)"},
          {"费用类型": "赎回费", "000044": "持有<7天: 1.5%", "000042": "持有<7天: 1.5%"}
        ]
      }
    }
  ],
  
  "charts": [
    {
      "id": "compare_nav_trend",
      "title": "净值走势对比",
      "type": "line",
      "description": "近1年累计收益率",
      "data": {
        "xAxis": ["2023-04", "2023-05", "...", "2024-04"],
        "series": [
          {
            "name": "000044",
            "data": [0, 2.5, "...", 15.2],
            "color": "#5470c6"
          },
          {
            "name": "000042",
            "data": [0, 2.1, "...", 12.5],
            "color": "#91cc75"
          },
          {
            "name": "同类平均",
            "data": [0, 1.8, "...", 10.5],
            "color": "#fac858",
            "style": "dashed"
          }
        ]
      }
    },
    {
      "id": "compare_style",
      "title": "投资风格对比",
      "type": "radar",
      "data": {
        "indicators": [
          {"name": "成长性", "max": 100},
          {"name": "价值性", "max": 100},
          {"name": "大盘", "max": 100},
          {"name": "中盘", "max": 100},
          {"name": "小盘", "max": 100}
        ],
        "series": [
          {"name": "000044", "data": [85, 30, 70, 20, 10], "color": "#5470c6"},
          {"name": "000042", "data": [60, 50, 50, 40, 10], "color": "#91cc75"}
        ]
      }
    }
  ]
}
```


## 实施方案

### 后端改造

#### 1. 修改 Agent 输出格式

在 `ProductInterpretAgent` 和 `ProductCompareAgent` 中：

```python
# backend/agents/fund_agent/product_interpret/agent.py

async def run(self, question: str, ctx: AgentRunContext) -> str:
    # ... 获取数据 ...
    
    # 构建结构化输出
    structured_output = {
        "type": "fund_analysis",
        "mode": "single",
        "summary": "",
        "cards": [],
        "sections": [],
        "charts": [],
        "text": ""
    }
    
    # 调用 LLM 生成结构化数据
    system_prompt = """
    你是基金分析专家。请输出 JSON 格式的分析结果，包含：
    1. cards: 置顶卡片（基本信息、费率、核心表现）
    2. sections: 分析模块（表格、文本）
    3. charts: 图表配置（环形图、折线图、雷达图）
    4. text: 完整文本（兜底）
    
    输出格式参考：{示例JSON}
    """
    
    result = await _llm_call_maybe_stream(...)
    
    # 解析 JSON
    try:
        structured_output = json.loads(result)
    except:
        # 兜底：返回纯文本
        structured_output["text"] = result
    
    return json.dumps(structured_output, ensure_ascii=False)
```

#### 2. 创建数据转换工具

```python
# backend/pkg/fund_formatter.py

def format_fund_cards(fund_data: dict) -> list[dict]:
    """将原始基金数据转换为卡片格式"""
    cards = []
    
    # 基本信息卡片
    if fund_data.get("basic_info"):
        cards.append({
            "id": f"basic_{fund_data['symbol']}",
            "title": "基本信息",
            "type": "basic",
            "data": extract_basic_info(fund_data["basic_info"])
        })
    
    # 费率卡片
    if fund_data.get("fee_info"):
        cards.append({
            "id": f"fee_{fund_data['symbol']}",
            "title": "费率信息",
            "type": "fee",
            "data": extract_fee_info(fund_data["fee_info"])
        })
    
    return cards

def format_performance_table(funds: list[dict]) -> dict:
    """生成业绩对比表格"""
    return {
        "id": "performance_compare",
        "title": "业绩对比",
        "type": "table",
        "table": {
            "headers": ["指标"] + [f["symbol"] for f in funds] + ["同类平均"],
            "rows": [
                {
                    "指标": "近1年收益",
                    **{f["symbol"]: f["return_1y"] for f in funds},
                    "同类平均": "10.5%"
                },
                # ...
            ]
        }
    }

def format_asset_chart(fund_data: dict) -> dict:
    """生成资产配置环形图"""
    asset_data = fund_data.get("asset_allocation", {})
    return {
        "id": f"asset_{fund_data['symbol']}",
        "title": "资产配置",
        "type": "pie",
        "data": {
            "labels": ["股票", "债券", "现金", "其他"],
            "values": extract_asset_values(asset_data),
            "colors": ["#5470c6", "#91cc75", "#fac858", "#ee6666"]
        }
    }
```


### 前端改造

#### 1. 解析结构化输出

```typescript
// frontend/src/utils/fundAnalysisParser.ts

interface FundAnalysisOutput {
  type: "fund_analysis";
  mode: "single" | "compare";
  summary: string;
  cards: InfoCard[];
  sections: AnalysisSection[];
  charts: ChartConfig[];
  text: string;
}

export function parseFundAnalysis(response: string): FundAnalysisOutput | null {
  try {
    const data = JSON.parse(response);
    if (data.type === "fund_analysis") {
      return data as FundAnalysisOutput;
    }
  } catch {
    // 兜底：返回 null，使用纯文本展示
  }
  return null;
}
```

#### 2. 渲染组件

```vue
<!-- frontend/src/components/FundAnalysis.vue -->
<template>
  <div class="fund-analysis">
    <!-- 摘要 -->
    <div class="summary-card">
      {{ analysis.summary }}
    </div>
    
    <!-- 置顶卡片 -->
    <div class="info-cards">
      <InfoCard
        v-for="card in analysis.cards"
        :key="card.id"
        :card="card"
      />
    </div>
    
    <!-- 分析模块 -->
    <div class="analysis-sections">
      <template v-for="section in analysis.sections" :key="section.id">
        <!-- 表格 -->
        <TableSection
          v-if="section.type === 'table'"
          :section="section"
        />
        
        <!-- 文本 -->
        <TextSection
          v-else-if="section.type === 'text'"
          :section="section"
        />
      </template>
    </div>
    
    <!-- 图表 -->
    <div class="charts-grid">
      <ChartRenderer
        v-for="chart in analysis.charts"
        :key="chart.id"
        :chart="chart"
      />
    </div>
    
    <!-- 兜底：纯文本 -->
    <div v-if="!analysis.cards.length" class="text-fallback">
      {{ analysis.text }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import InfoCard from './InfoCard.vue';
import TableSection from './TableSection.vue';
import TextSection from './TextSection.vue';
import ChartRenderer from './ChartRenderer.vue';

const props = defineProps<{
  analysis: FundAnalysisOutput;
}>();
</script>
```


#### 3. 卡片组件

```vue
<!-- frontend/src/components/InfoCard.vue -->
<template>
  <div class="info-card" :class="`card-${card.type}`">
    <h3 class="card-title">{{ card.title }}</h3>
    <div class="card-content">
      <div
        v-for="(value, key) in card.data"
        :key="key"
        class="card-item"
      >
        <span class="item-label">{{ formatLabel(key) }}</span>
        <span class="item-value">{{ value }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.card-basic { border-left: 4px solid #5470c6; }
.card-performance { border-left: 4px solid #91cc75; }
.card-risk { border-left: 4px solid #ee6666; }
.card-fee { border-left: 4px solid #fac858; }

.card-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.item-label {
  color: #666;
  font-size: 14px;
}

.item-value {
  color: #333;
  font-weight: 500;
}
</style>
```

#### 4. 表格组件

```vue
<!-- frontend/src/components/TableSection.vue -->
<template>
  <div class="table-section">
    <h3>{{ section.title }}</h3>
    <p v-if="section.description" class="description">
      {{ section.description }}
    </p>
    
    <table class="compare-table">
      <thead>
        <tr>
          <th v-for="header in section.table.headers" :key="header">
            {{ header }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, idx) in section.table.rows" :key="idx">
          <td
            v-for="header in section.table.headers"
            :key="header"
            :class="{ highlight: isHighlight(header) }"
          >
            {{ row[header] }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.compare-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 16px;
}

.compare-table th {
  background: #f5f5f5;
  padding: 12px;
  text-align: left;
  font-weight: 600;
}

.compare-table td {
  padding: 12px;
  border-bottom: 1px solid #e8e8e8;
}

.compare-table td.highlight {
  background: #e6f7ff;
  font-weight: 500;
}
</style>
```


#### 5. 图表组件（使用 ECharts）

```vue
<!-- frontend/src/components/ChartRenderer.vue -->
<template>
  <div class="chart-container">
    <h3>{{ chart.title }}</h3>
    <p v-if="chart.description" class="description">
      {{ chart.description }}
    </p>
    <div ref="chartRef" class="chart" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import * as echarts from 'echarts';

const props = defineProps<{
  chart: ChartConfig;
}>();

const chartRef = ref<HTMLElement>();
let chartInstance: echarts.ECharts;

onMounted(() => {
  if (chartRef.value) {
    chartInstance = echarts.init(chartRef.value);
    renderChart();
  }
});

function renderChart() {
  let option: any;
  
  switch (props.chart.type) {
    case 'pie':
      option = getPieOption();
      break;
    case 'line':
      option = getLineOption();
      break;
    case 'radar':
      option = getRadarOption();
      break;
  }
  
  chartInstance.setOption(option);
}

function getPieOption() {
  const { data } = props.chart;
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['50%', '70%'],
      data: data.labels.map((label: string, idx: number) => ({
        name: label,
        value: data.values[idx],
        itemStyle: { color: data.colors[idx] }
      })),
      label: {
        formatter: '{b}: {d}%'
      }
    }]
  };
}

function getLineOption() {
  const { data } = props.chart;
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: data.series.map((s: any) => s.name) },
    xAxis: {
      type: 'category',
      data: data.xAxis
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%' }
    },
    series: data.series.map((s: any) => ({
      name: s.name,
      type: 'line',
      data: s.data,
      lineStyle: {
        color: s.color,
        type: s.style === 'dashed' ? 'dashed' : 'solid'
      },
      itemStyle: { color: s.color }
    }))
  };
}

function getRadarOption() {
  const { data } = props.chart;
  return {
    tooltip: {},
    legend: { data: data.series.map((s: any) => s.name) },
    radar: { indicator: data.indicators },
    series: [{
      type: 'radar',
      data: data.series.map((s: any) => ({
        name: s.name,
        value: s.data,
        itemStyle: { color: s.color }
      }))
    }]
  };
}
</script>

<style scoped>
.chart-container {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.chart {
  width: 100%;
  height: 300px;
}
</style>
```


## 实施步骤

### Phase 1：后端结构化输出（1-2天）

1. ✅ 创建数据格式定义（TypeScript 接口）
2. ✅ 创建数据转换工具 `backend/pkg/fund_formatter.py`
3. ✅ 修改 `ProductInterpretAgent` 输出结构化 JSON
4. ✅ 修改 `ProductCompareAgent` 输出结构化 JSON
5. ✅ 测试 JSON 输出格式

### Phase 2：前端渲染组件（2-3天）

1. ✅ 创建解析工具 `fundAnalysisParser.ts`
2. ✅ 创建 `InfoCard.vue` 组件
3. ✅ 创建 `TableSection.vue` 组件
4. ✅ 创建 `ChartRenderer.vue` 组件（集成 ECharts）
5. ✅ 创建主容器 `FundAnalysis.vue`
6. ✅ 集成到 `ChatView.vue`

### Phase 3：优化与完善（1-2天）

1. ✅ 添加响应式布局（移动端适配）
2. ✅ 添加图表交互（点击、缩放）
3. ✅ 添加数据导出功能（PDF、Excel）
4. ✅ 性能优化（图表懒加载）
5. ✅ 兜底处理（纯文本展示）

## 技术栈

- **后端**：Python + JSON 序列化
- **前端**：Vue 3 + TypeScript + ECharts
- **样式**：CSS Grid + Flexbox

## 优势

1. **用户体验**：
   - 信息密度高，一屏展示更多内容
   - 图形化展示，降低认知负担
   - 对比清晰，决策更快

2. **可扩展性**：
   - 结构化数据易于扩展新图表类型
   - 前后端分离，独立迭代
   - 支持多种输出格式（JSON、Markdown）

3. **兼容性**：
   - 保留纯文本兜底，确保稳定性
   - 渐进式增强，老版本前端仍可用

## 注意事项

1. **LLM 输出稳定性**：
   - LLM 可能输出不规范的 JSON
   - 需要严格的 JSON 校验和修复
   - 提供详细的 Prompt 示例

2. **数据完整性**：
   - 某些基金可能缺少部分数据
   - 需要优雅降级（隐藏缺失模块）

3. **性能**：
   - 图表渲染可能影响性能
   - 使用虚拟滚动和懒加载

## 相关文件

- `backend/pkg/fund_formatter.py` - 数据转换工具（新增）
- `backend/agents/fund_agent/product_interpret/agent.py` - 单只基金解读（修改）
- `backend/agents/fund_agent/product_compare/agent.py` - 基金对比（修改）
- `frontend/src/utils/fundAnalysisParser.ts` - 解析工具（新增）
- `frontend/src/components/FundAnalysis.vue` - 主容器（新增）
- `frontend/src/components/InfoCard.vue` - 卡片组件（新增）
- `frontend/src/components/TableSection.vue` - 表格组件（新增）
- `frontend/src/components/ChartRenderer.vue` - 图表组件（新增）

## 更新日期

2026-04-10
