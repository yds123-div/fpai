<template>
  <div class="chart-container">
    <div class="chart-title">{{ chart.title }}</div>
    <p v-if="chart.description" class="chart-desc">{{ chart.description }}</p>
    <div v-if="showRangeTabs" class="range-tabs">
      <button
        v-for="opt in periodOptions"
        :key="opt"
        class="range-tab"
        :class="{ active: opt === selectedPeriod }"
        @click="onSelectPeriod(opt)"
      >
        {{ opt }}
      </button>
    </div>
    <div ref="chartEl" class="chart-canvas" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart, LineChart, BarChart, RadarChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, RadarComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ChartConfig, PieChartData, LineChartData, RadarChartData } from '@/types/fundAnalysis'
import type { EChartsCoreOption } from 'echarts/core'

echarts.use([
  PieChart, LineChart, BarChart, RadarChart,
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, RadarComponent, CanvasRenderer,
])

const props = defineProps<{ chart: ChartConfig }>()

const chartEl = ref<HTMLElement>()
let instance: echarts.ECharts | null = null
const selectedPeriod = ref('')

const periodOptions = computed(() => {
  const options = props.chart.options as Record<string, unknown> | undefined
  const raw = options?.periodOptions
  return Array.isArray(raw) ? raw.map(v => String(v)) : []
})

const showRangeTabs = computed(() => props.chart.id.startsWith('nav_') && periodOptions.value.length > 0)

function getEffectiveLineData(): LineChartData {
  const options = props.chart.options as Record<string, unknown> | undefined
  const rangeData = options?.rangeData as Record<string, unknown> | undefined
  if (rangeData && selectedPeriod.value) {
    const picked = rangeData[selectedPeriod.value] as LineChartData | undefined
    if (picked && Array.isArray(picked.xAxis) && Array.isArray(picked.series)) {
      return picked
    }
  }
  return props.chart.data as LineChartData
}

function onSelectPeriod(period: string) {
  selectedPeriod.value = period
  nextTick(render)
}

function buildPieOption(data: PieChartData | any): EChartsCoreOption {
  // 兼容两种数据格式
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

function buildDonutOption(data: any): EChartsCoreOption {
  // 环形图与饼图类似，但内圈更大
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

function buildLineOption(data: LineChartData): EChartsCoreOption {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: data.series.map(s => s.name), bottom: 0 },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: data.xAxis, boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
    series: data.series.map(s => ({
      name: s.name,
      type: 'line' as const,
      data: s.data,
      smooth: true,
      lineStyle: {
        color: s.color,
        type: s.style === 'dashed' ? ('dashed' as const) : ('solid' as const),
      },
      itemStyle: s.color ? { color: s.color } : undefined,
    })),
  }
}

function buildRadarOption(data: RadarChartData): EChartsCoreOption {
  return {
    tooltip: {},
    legend: { data: data.series.map(s => s.name), bottom: 0 },
    radar: { indicator: data.indicators },
    series: [{
      type: 'radar',
      data: data.series.map(s => ({
        name: s.name,
        value: s.data,
        itemStyle: s.color ? { color: s.color } : undefined,
        areaStyle: { opacity: 0.15 },
      })),
    }],
  }
}

function render() {
  if (!chartEl.value) return
  if (!instance) {
    instance = echarts.init(chartEl.value)
  }
  let option: EChartsCoreOption | null = null
  try {
    switch (props.chart.type) {
      case 'pie':
        option = buildPieOption(props.chart.data as PieChartData)
        break
      case 'donut':
        option = buildDonutOption(props.chart.data)
        break
      case 'line':
        option = buildLineOption(getEffectiveLineData())
        break
      case 'radar':
        option = buildRadarOption(props.chart.data as RadarChartData)
        break
      case 'bar':
        option = buildLineOption(props.chart.data as LineChartData)
        if (option.series && Array.isArray(option.series)) {
          option.series = (option.series as Array<Record<string, unknown>>).map(s => ({ ...s, type: 'bar' }))
        }
        break
      default:
        console.warn(`[ChartRenderer] Unsupported chart type: ${props.chart.type}`)
    }
    if (option) instance.setOption(option, true)
  } catch (e) {
    console.warn('[ChartRenderer] render error:', e, props.chart)
  }
}

function handleResize() {
  instance?.resize()
}

onMounted(() => {
  nextTick(render)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  instance?.dispose()
  instance = null
})

watch(() => props.chart, () => nextTick(render), { deep: true })

watch(
  () => props.chart,
  () => {
    const options = props.chart.options as Record<string, unknown> | undefined
    const defaultPeriod = String(options?.defaultPeriod || '')
    if (defaultPeriod && periodOptions.value.includes(defaultPeriod)) {
      selectedPeriod.value = defaultPeriod
    } else {
      selectedPeriod.value = periodOptions.value[0] || ''
    }
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
.chart-container {
  background: var(--card-bg, #fff);
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.chart-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--text-primary, #1a1a1a);
}
.chart-desc {
  font-size: 12px;
  color: var(--text-secondary, #888);
  margin-bottom: 8px;
}
.chart-canvas {
  width: 100%;
  height: 280px;
}

.range-tabs {
  display: flex;
  gap: 8px;
  margin: 8px 0 10px;
  flex-wrap: wrap;
}

.range-tab {
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #333;
  border-radius: 16px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}

.range-tab.active {
  border-color: #1677ff;
  color: #1677ff;
  background: #e6f4ff;
}
</style>
