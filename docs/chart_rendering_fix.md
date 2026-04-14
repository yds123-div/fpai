# 基金对比图表渲染问题修复

## 问题描述

用户反馈基金对比报告中：
1. **图表完全不显示** - 后端生成了6个图表，但前端一个都没渲染
2. **表格显示不完整** - 只显示了"基本信息对比"表格，缺少"业绩对比"和"费率对比"表格
3. **表格指标太少** - 基本信息表格只显示了7行，实际应该有9行

## 根本原因

### 1. 数据格式不匹配

**后端生成的格式**（backend/pkg/fund_formatter.py）：
```python
# 饼图/环形图
{
    "type": "pie" | "donut",
    "data": {
        "series": [
            {"name": "债券", "value": 84.8, "color": "#5470c6"},
            {"name": "现金", "value": 15.2, "color": "#91cc75"}
        ]
    }
}

# 折线图/柱状图
{
    "type": "line" | "bar",
    "data": {
        "xAxis": ["近1月", "近3月", "近6月", "近1年"],
        "series": [
            {"name": "000009", "data": [0.29, 0.89, 1.71, 3.63], "color": "#5470c6"}
        ]
    }
}
```

**前端期望的格式**（frontend/src/components/fund/ChartRenderer.vue）：
```typescript
// 饼图
{
    type: "pie",
    data: {
        labels: ["债券", "现金"],
        values: [84.8, 15.2],
        colors: ["#5470c6", "#91cc75"]
    }
}

// 折线图（柱状图格式相同）
{
    type: "line",
    data: {
        xAxis: ["近1月", "近3月"],
        series: [
            {name: "000009", data: [0.29, 0.89], color: "#5470c6"}
        ]
    }
}
```

### 2. 缺少 donut 类型支持

前端 `ChartRenderer` 组件的 switch 语句中没有处理 `donut` 类型，导致环形图无法渲染。

### 3. 错误处理不完善

图表渲染失败时，错误被静默捕获，没有在控制台输出详细信息，导致难以排查。

## 修复方案

### 1. 修改 ChartRenderer.vue

#### 1.1 添加 donut 类型支持

```typescript
function buildDonutOption(data: any): EChartsCoreOption {
  let pieData: Array<{ name: string; value: number; itemStyle?: { color: string } }>
  
  if ('series' in data && Array.isArray(data.series)) {
    pieData = data.series.map((item: any) => ({
      name: item.name,
      value: item.value,
      itemStyle: item.color ? { color: item.color } : undefined,
    }))
  } else {
    pieData = []
  }

  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, left: 'center' },
    series: [{
      type: 'pie',
      radius: ['50%', '75%'],  // 环形图的内外半径
      avoidLabelOverlap: true,
      label: { 
        formatter: '{b}\n{d}%', 
        fontSize: 12,
        position: 'outside'
      },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold' }
      },
      data: pieData,
    }],
  }
}
```

#### 1.2 兼容两种数据格式

修改 `buildPieOption` 函数，同时支持后端和前端格式：

```typescript
function buildPieOption(data: PieChartData | any): EChartsCoreOption {
  let pieData: Array<{ name: string; value: number; itemStyle?: { color: string } }>
  
  if ('series' in data && Array.isArray(data.series)) {
    // 后端格式: { series: [{ name, value, color }] }
    pieData = data.series.map((item: any) => ({
      name: item.name,
      value: item.value,
      itemStyle: item.color ? { color: item.color } : undefined,
    }))
  } else if ('labels' in data && 'values' in data) {
    // 前端格式: { labels: [], values: [], colors: [] }
    pieData = data.labels.map((name: string, i: number) => ({
      name,
      value: data.values[i],
      itemStyle: data.colors?.[i] ? { color: data.colors[i] } : undefined,
    }))
  } else {
    pieData = []
  }

  return {
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{d}%', fontSize: 12 },
      data: pieData,
    }],
  }
}
```

#### 1.3 改进错误处理

```typescript
function render() {
  // ...
  try {
    switch (props.chart.type) {
      case 'pie':
        option = buildPieOption(props.chart.data as PieChartData)
        break
      case 'donut':
        option = buildDonutOption(props.chart.data)
        break
      // ... 其他类型
      default:
        console.warn(`[ChartRenderer] Unsupported chart type: ${props.chart.type}`)
    }
    if (option) instance.setOption(option, true)
  } catch (e) {
    console.warn('[ChartRenderer] render error:', e, props.chart)  // 输出完整的图表配置
  }
}
```

### 2. 更新类型定义

修改 `frontend/src/types/fundAnalysis.ts`，添加 `donut` 类型：

```typescript
export interface ChartConfig {
  id: string
  title: string
  type: 'pie' | 'donut' | 'line' | 'bar' | 'radar'  // 添加 donut
  description?: string
  data: PieChartData | LineChartData | RadarChartData | Record<string, unknown>
  options?: Record<string, unknown>
}
```

## 验证方法

### 1. 后端调试

运行 `backend/debug_compare_output.py` 验证后端输出：

```bash
cd backend
python debug_compare_output.py
```

预期输出：
- 图表数量: 6
- Sections 数量: 5（3个表格 + 2个文本）
- 完整的 JSON 输出保存到 `debug_compare_output.json`

### 2. 前端测试

打开 `frontend/test-chart-renderer.html` 在浏览器中查看：
- 环形图（费率结构）
- 柱状图（收益率对比）
- 柱状图（风险指标对比）
- 饼图（资产配置）

### 3. 集成测试

1. 启动后端服务
2. 启动前端开发服务器
3. 发起基金对比请求
4. 检查浏览器控制台是否有错误
5. 验证所有图表和表格是否正常显示

## 预期效果

修复后，基金对比报告应该包含：

### 图表（6个）
1. ✅ 净值走势折线图 - 展示长期趋势
2. ✅ 收益率柱状图 - 展示各期收益对比
3. ✅ 风险指标柱状图 - 展示风险指标对比
4. ✅ 投资风格雷达图 - 展示投资风格差异
5. ✅ 资产配置饼图（每只基金一个）
6. ✅ 费率环形图 - 展示费率结构

### 表格（3个）
1. ✅ 基本信息对比表（9行）- 基金规模、经理、风险等级等
2. ✅ 业绩对比表（25行）- 各期收益率、风险指标等
3. ✅ 费率对比表（3-5行）- 管理费、托管费等

## 后续优化建议

### 1. 统一数据格式
建议前后端统一使用后端格式，避免兼容性代码：
- 饼图/环形图: `{ series: [{ name, value, color }] }`
- 折线图/柱状图: `{ xAxis: [], series: [{ name, data, color }] }`

### 2. 增强错误提示
在图表渲染失败时，显示友好的错误提示而不是空白区域。

### 3. 添加加载状态
使用 Suspense 的 fallback 显示加载动画。

### 4. 响应式优化
在移动端自动调整图表大小和布局。

### 5. 性能优化
- 使用虚拟滚动处理大量数据
- 图表懒加载，只渲染可见区域的图表

## 相关文件

- `backend/pkg/fund_formatter.py` - 后端图表生成逻辑
- `frontend/src/components/fund/ChartRenderer.vue` - 前端图表渲染组件
- `frontend/src/types/fundAnalysis.ts` - 类型定义
- `frontend/src/components/fund/FundAnalysis.vue` - 主渲染组件
- `backend/debug_compare_output.py` - 调试脚本
- `frontend/test-chart-renderer.html` - 前端测试页面

## 修复时间

- 2025-01-XX
- 修复人: AI Assistant
