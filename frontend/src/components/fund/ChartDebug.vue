<template>
  <div v-if="showDebug" class="chart-debug">
    <div class="debug-header" @click="collapsed = !collapsed">
      <span>🔍 图表调试信息</span>
      <span>{{ collapsed ? '▼' : '▲' }}</span>
    </div>
    <div v-if="!collapsed" class="debug-content">
      <p><strong>图表ID:</strong> {{ chart.id }}</p>
      <p><strong>图表类型:</strong> {{ chart.type }}</p>
      <p><strong>图表标题:</strong> {{ chart.title }}</p>
      <p><strong>数据格式:</strong></p>
      <pre>{{ JSON.stringify(chart.data, null, 2).substring(0, 500) }}</pre>
      <p v-if="error" class="error">❌ 错误: {{ error }}</p>
      <p v-else class="success">✅ 数据格式正确</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ChartConfig } from '@/types/fundAnalysis'

const props = defineProps<{ chart: ChartConfig }>()

const collapsed = ref(true)
const showDebug = ref(import.meta.env.DEV) // 只在开发环境显示

const error = computed(() => {
  const { type, data } = props.chart
  
  if (!data) return '缺少 data 字段'
  
  if (type === 'pie' || type === 'donut') {
    const d = data as Record<string, unknown>
    if (!('series' in d) && !('labels' in d)) {
      return '饼图/环形图需要 series 或 labels 字段'
    }
  } else if (type === 'line' || type === 'bar') {
    const d = data as Record<string, unknown>
    if (!('xAxis' in d) || !('series' in d)) {
      return '折线图/柱状图需要 xAxis 和 series 字段'
    }
  } else if (type === 'radar') {
    const d = data as Record<string, unknown>
    if (!('indicators' in d) || !('series' in d)) {
      return '雷达图需要 indicators 和 series 字段'
    }
  }
  
  return null
})
</script>

<style scoped>
.chart-debug {
  border: 2px solid #ff6b6b;
  border-radius: 4px;
  margin: 10px 0;
  background: #fff5f5;
}

.debug-header {
  padding: 8px 12px;
  background: #ff6b6b;
  color: white;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.debug-content {
  padding: 12px;
  font-size: 12px;
}

.debug-content p {
  margin: 4px 0;
}

.debug-content pre {
  background: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 11px;
}

.error {
  color: #ff6b6b;
  font-weight: bold;
}

.success {
  color: #51cf66;
  font-weight: bold;
}
</style>
