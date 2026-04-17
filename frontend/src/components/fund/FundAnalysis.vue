<template>
  <div class="fund-analysis">
    <div v-if="visibleCards.length" class="fa-cards">
      <InfoCard v-for="card in visibleCards" :key="card.id" :card="card" />
    </div>

    <div v-if="visibleSections.length" class="fa-sections">
      <template v-for="section in visibleSections" :key="section.id">
        <TableSectionVue v-if="section.type === 'table'" :section="section" />
        <PerformanceSummary
          v-else-if="section.type === 'text' && isPerformanceTitle(section.title)"
          :section="section"
        />
        <TextSectionVue v-else-if="section.type === 'text'" :section="section" />
      </template>
    </div>

    <div v-if="visibleCharts.length" class="fa-charts">
      <div v-for="chart in visibleCharts" :key="chart.id" class="chart-wrapper">
        <Suspense>
          <ChartRenderer :chart="chart" />
          <template #fallback>
            <div class="chart-loading">图表加载中...</div>
          </template>
        </Suspense>
      </div>
    </div>
    <div v-else class="no-charts">
      <p><span class="no-chart-icon" aria-hidden="true">!</span> 没有图表数据</p>
      <p>当前问题未返回可展示的图表。</p>
    </div>

    <div
      v-if="!analysis.cards.length && !analysis.sections.length && !analysis.charts.length && analysis.text"
      class="fa-fallback"
      style="white-space: pre-wrap"
    >
      {{ analysis.text }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, watchEffect } from 'vue'
import type { AnalysisSection, ChartConfig, FundAnalysisOutput } from '@/types/fundAnalysis'
import InfoCard from './InfoCard.vue'
import TableSectionVue from './TableSection.vue'
import TextSectionVue from './TextSection.vue'
import PerformanceSummary from './PerformanceSummary.vue'

const ChartRenderer = defineAsyncComponent(() => import('./ChartRenderer.vue'))

const props = defineProps<{ analysis: FundAnalysisOutput }>()

const visibleCards = computed(() => props.analysis.cards || [])

function isBasicInfoTitle(title: string): boolean {
  return /基本信息|basic/i.test(title || '')
}

function isPerformanceTitle(title: string): boolean {
  return /业绩表现|performance/i.test(title || '')
}

function sectionSignature(section: AnalysisSection): string {
  if (section.type === 'table') {
    const headers = section.table?.headers || []
    const firstRow = section.table?.rows?.[0] || {}
    return `table:${section.title}:${JSON.stringify(headers)}:${JSON.stringify(firstRow)}`
  }
  return `text:${section.title}:${(section.content || '').slice(0, 120)}`
}

const visibleSections = computed(() => {
  const sections = props.analysis.sections || []
  const hasCards = visibleCards.value.length > 0
  const seen = new Set<string>()

  return sections.filter((section) => {
    const signature = sectionSignature(section)
    if (seen.has(signature)) return false
    seen.add(signature)

    // When cards already show basic info, hide duplicated basic-info table sections.
    if (hasCards && section.type === 'table' && isBasicInfoTitle(section.title)) {
      return false
    }

    return true
  })
})

function extractFundCodeFromSections(sections: AnalysisSection[]): string {
  const table = (sections || []).find(
    (s): s is Extract<AnalysisSection, { type: 'table' }> =>
      s.type === 'table' && /基金详细信息/i.test(s.title || ''),
  )
  const rows = table?.table?.rows || []
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue
    const k = String((row as Record<string, unknown>)['字段'] ?? '').trim()
    const v = String((row as Record<string, unknown>)['内容'] ?? '').trim()
    if (k === '基金代码' && /^\d{6}$/.test(v)) return v
  }
  return ''
}

function isLowSignalChart(chart: ChartConfig): boolean {
  const id = chart.id || ''
  const title = chart.title || ''
  // 低信息增量图先不面向用户展示，避免“图看起来高级但帮助决策有限”。
  return /^style_radar$/i.test(id)
}

const visibleCharts = computed(() => {
  const fundCode = extractFundCodeFromSections(props.analysis.sections || [])
  return (props.analysis.charts || [])
    .filter((c) => !isLowSignalChart(c))
    .map((c) => {
      const options = (c.options || {}) as Record<string, unknown>
      // 仅为净值图补充 fundCode，供按周期懒加载使用
      if (fundCode && String(c.id || '').startsWith('nav_')) {
        return { ...c, options: { ...options, fundCode } }
      }
      return c
    })
})

watchEffect(() => {
  const sections = props.analysis.sections || []
  const perfSections = sections.filter(
    s => s.type === 'text' && isPerformanceTitle((s as { title?: string }).title || ''),
  )
  void perfSections
})
</script>

<style scoped>
.fund-analysis {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0;
}

.fa-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.fa-sections {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fa-charts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.chart-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.no-charts {
  padding: 20px;
  text-align: center;
  background: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 8px;
  color: #856404;
}

.no-chart-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #faad14;
  color: #fff;
  font-size: 12px;
  line-height: 1;
  margin-right: 6px;
  font-weight: 700;
}

.fa-fallback {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary, #333);
}

.chart-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  background: var(--card-bg, #fff);
  border-radius: 10px;
  color: var(--text-secondary, #999);
  font-size: 13px;
}

@media (max-width: 768px) {
  .fa-cards {
    grid-template-columns: 1fr;
  }

  .fa-charts {
    grid-template-columns: 1fr;
  }
}
</style>
