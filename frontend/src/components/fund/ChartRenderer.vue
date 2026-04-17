<template>
  <div class="chart-container">
    <div class="chart-title">{{ displayTitle }}</div>
    <p v-if="chart.description" class="chart-desc">{{ chart.description }}</p>
    <div v-if="showRangeTabs" class="range-tabs">
      <button
        v-for="opt in periodOptions"
        :key="opt"
        class="range-tab"
        :class="{ active: opt === selectedPeriod }"
        :disabled="isLoading && opt !== selectedPeriod"
        @click="onSelectPeriod(opt)"
      >
        {{ opt }}
      </button>
    </div>
    <p v-if="showRangeTabs" class="range-hint">
      <template v-if="isLoading">正在加载 {{ selectedPeriod }}…</template>
      <template v-else-if="rangeHint">{{ rangeHint }}</template>
      <template v-else>暂无该项数据</template>
    </p>
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
import { getFundNavByPeriod, type FundNavByPeriodResponse, type FundNavPeriod } from '@/api/funds'

echarts.use([
  PieChart, LineChart, BarChart, RadarChart,
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, RadarComponent, CanvasRenderer,
])

const props = defineProps<{ chart: ChartConfig }>()

const chartEl = ref<HTMLElement>()
let instance: echarts.ECharts | null = null
const selectedPeriod = ref('')
const isLoading = ref(false)
const lastError = ref('')
const requestSeq = ref(0)
const activeController = ref<AbortController | null>(null)
const navLineData = ref<LineChartData | null>(null)

type CachedNav = {
  fetchedAt: number
  start: string
  end: string
  points: number
  data: LineChartData
}
const navCache = ref<Record<string, CachedNav>>({})
const NAV_CACHE_TTL_MS = 60_000

const periodOptions = computed(() => {
  const options = props.chart.options as Record<string, unknown> | undefined
  const raw = options?.periodOptions
  return Array.isArray(raw) ? raw.map(v => String(v)) : []
})

const isNavChart = computed(() => props.chart.id.startsWith('nav_'))
const showRangeTabs = computed(() => isNavChart.value && periodOptions.value.length > 0)
const displayTitle = computed(() => {
  if (!showRangeTabs.value || !selectedPeriod.value) return props.chart.title
  return `${props.chart.title}（${selectedPeriod.value}）`
})

function getEffectiveLineData(): LineChartData {
  if (isNavChart.value && navLineData.value) return navLineData.value
  return props.chart.data as LineChartData
}

function getFundCode(): string {
  const options = props.chart.options as Record<string, unknown> | undefined
  const fromOptions = String(options?.fundCode || '').trim()
  if (/^\d{6}$/.test(fromOptions)) return fromOptions
  const fromChartId = String(props.chart.id || '').match(/^nav_(\d{6})$/)?.[1] || ''
  return /^\d{6}$/.test(fromChartId) ? fromChartId : ''
}

function normalizePeriod(p: string): FundNavPeriod | null {
  if (p === '近1月' || p === '近3月' || p === '近1年' || p === '成立以来') return p
  return null
}

function getRangeHintFromCache(p: string): string {
  const cached = navCache.value[p]
  if (!cached) return ''
  const { start, end, points } = cached
  if (!start || !end) return ''
  return `${p} · ${start} ~ ${end}（${points}个交易日）`
}

const rangeHint = computed(() => {
  if (!showRangeTabs.value || !selectedPeriod.value) return ''
  if (lastError.value) return `${selectedPeriod.value} ${lastError.value}（点击重试）`
  return getRangeHintFromCache(selectedPeriod.value)
})

function shouldUseCache(p: string): boolean {
  const cached = navCache.value[p]
  if (!cached) return false
  return Date.now() - cached.fetchedAt <= NAV_CACHE_TTL_MS
}

function getRangeDataFromOptions(period: string): LineChartData | null {
  const options = props.chart.options as Record<string, unknown> | undefined
  const rangeData = options?.rangeData as Record<string, unknown> | undefined
  if (!rangeData || typeof rangeData !== 'object') return null
  const one = rangeData[period] as LineChartData | undefined
  if (!one || typeof one !== 'object') return null
  const xAxis = Array.isArray(one.xAxis) ? one.xAxis : []
  const series = Array.isArray(one.series) ? one.series : []
  if (!xAxis.length || !series.length) return null
  return one
}

async function loadNavPeriod(period: string) {
  if (!isNavChart.value) return
  const normalized = normalizePeriod(period)
  if (!normalized) return
  const code = getFundCode()
  if (!code) {
    lastError.value = '缺少基金代码'
    return
  }

  // 优先使用后端首轮已返回的分段数据，避免切换时再次请求
  const localRangeData = getRangeDataFromOptions(period)
  if (localRangeData) {
    const xAxis = Array.isArray(localRangeData.xAxis) ? localRangeData.xAxis : []
    navCache.value = {
      ...navCache.value,
      [period]: {
        fetchedAt: Date.now(),
        start: String(xAxis[0] || ''),
        end: String(xAxis[xAxis.length - 1] || ''),
        points: xAxis.length,
        data: localRangeData,
      },
    }
    navLineData.value = localRangeData
    nextTick(render)
    return
  }

  // cache hit
  if (shouldUseCache(period)) {
    const cached = navCache.value[period]
    if (cached?.data) {
      navLineData.value = cached.data
      nextTick(render)
    }
    return
  }

  // cancel previous in-flight request
  activeController.value?.abort()
  const controller = new AbortController()
  activeController.value = controller

  const seq = ++requestSeq.value
  isLoading.value = true
  lastError.value = ''

  try {
    const res: FundNavByPeriodResponse = await getFundNavByPeriod(code, normalized, { signal: controller.signal })
    // last-write-wins：只认最后一次点击
    if (seq !== requestSeq.value) return
    if (selectedPeriod.value !== period) return

    const chartData = res?.chart?.data as unknown as LineChartData
    const xAxis = Array.isArray(chartData?.xAxis) ? chartData.xAxis : []
    const series = Array.isArray(chartData?.series) ? chartData.series : []
    if (!xAxis.length || !series.length) {
      lastError.value = '暂无数据'
      return
    }

    navCache.value = {
      ...navCache.value,
      [period]: {
        fetchedAt: Date.now(),
        start: res.start || String(xAxis[0] || ''),
        end: res.end || String(xAxis[xAxis.length - 1] || ''),
        points: typeof res.points === 'number' ? res.points : xAxis.length,
        data: chartData,
      },
    }

    // 更新图数据（仅内部状态，不修改 props）
    navLineData.value = chartData
    nextTick(render)
  } catch (e: any) {
    if (e?.name === 'CanceledError' || e?.name === 'AbortError') {
      // 用户已切换到其它周期：静默
      return
    }
    lastError.value = e?.message ? String(e.message) : '加载失败'
  } finally {
    // 只有当前请求才能收尾
    if (seq === requestSeq.value) {
      isLoading.value = false
    }
  }
}

function onSelectPeriod(period: string) {
  selectedPeriod.value = period
  if (showRangeTabs.value) {
    void loadNavPeriod(period)
  }
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
    navLineData.value = null
    const options = props.chart.options as Record<string, unknown> | undefined
    const defaultPeriod = String(options?.defaultPeriod || '')
    if (defaultPeriod && periodOptions.value.includes(defaultPeriod)) {
      selectedPeriod.value = defaultPeriod
    } else {
      selectedPeriod.value = periodOptions.value[0] || ''
    }

    // 初始化：默认周期先按需拉一次，确保“口径提示 + 数据一致”
    if (showRangeTabs.value && selectedPeriod.value) {
      void loadNavPeriod(selectedPeriod.value)
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
  margin: 8px 0 6px;
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

.range-tab:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.range-hint {
  margin: 0 0 8px;
  color: #64748b;
  font-size: 12px;
}
</style>
