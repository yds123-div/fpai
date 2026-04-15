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

    <div v-if="analysis.charts.length" class="fa-charts">
      <div v-for="chart in analysis.charts" :key="chart.id" class="chart-wrapper">
        <component v-if="isDev && ChartDebug" :is="ChartDebug" :chart="chart" />
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
      <p>charts 数组长度: {{ analysis.charts?.length || 0 }}</p>
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
import type { AnalysisSection, FundAnalysisOutput } from '@/types/fundAnalysis'
import InfoCard from './InfoCard.vue'
import TableSectionVue from './TableSection.vue'
import TextSectionVue from './TextSection.vue'
import PerformanceSummary from './PerformanceSummary.vue'

const ChartRenderer = defineAsyncComponent(() => import('./ChartRenderer.vue'))
const isDev = import.meta.env.DEV
const ChartDebug = isDev ? defineAsyncComponent(() => import('./ChartDebug.vue')) : null

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
