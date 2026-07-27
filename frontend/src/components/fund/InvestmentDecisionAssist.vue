<template>
  <div class="assist-page">
    <!-- A. 一句话结论 -->
    <section class="sec sec-conclusion">
      <div class="sec-title">一句话结论</div>
      <div class="sec-body">{{ conclusion }}</div>
    </section>

    <!-- B. 适合谁 / 不适合谁 -->
    <section class="sec sec-audience">
      <div class="sec-title">适合谁 / 不适合谁</div>
      <div class="aud-row">
        <div class="aud-block">
          <div class="aud-label">适合人群</div>
          <div class="aud-text">{{ fitText }}</div>
        </div>
        <div class="aud-block">
          <div class="aud-label">不适合人群</div>
          <div class="aud-text">{{ unfitText }}</div>
        </div>
      </div>
    </section>

    <!-- C. 关键指标卡片 -->
    <section class="sec sec-metrics">
      <div class="sec-title">关键指标（首屏证据）</div>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">费率</div>
          <div class="metric-value">{{ feeText }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">近1年收益及同类分位</div>
          <div class="metric-value">{{ ret1yText }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">近3年收益及同类分位</div>
          <div class="metric-value">{{ ret3yText }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">最大回撤</div>
          <div class="metric-value">{{ maxDrawdownText }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">规模</div>
          <div class="metric-value">{{ scaleText }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">跟踪误差</div>
          <div class="metric-value">{{ trackingErrorText }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">跟踪偏离</div>
          <div class="metric-value">{{ trackingDeviationText }}</div>
        </div>
      </div>
    </section>

    <!-- D. 为什么可以关注 -->
    <section class="sec sec-why">
      <div class="sec-title">为什么可以关注</div>
      <div class="sec-body">
        <p v-for="(line, i) in whyLines" :key="i" class="p-line">{{ line }}</p>
      </div>
    </section>

    <!-- E. 为什么要谨慎 -->
    <section class="sec sec-risk">
      <div class="sec-title">为什么要谨慎</div>
      <div class="sec-body">
        <p v-for="(line, i) in riskLines" :key="i" class="p-line">{{ line }}</p>
      </div>
    </section>

    <!-- F. 替代品比较 -->
    <section class="sec sec-compare">
      <div class="sec-title">替代品比较</div>
      <div class="sec-body">
        <p v-for="(line, i) in compareLines" :key="i" class="p-line">{{ line }}</p>
        <p v-if="!compareLines.length" class="p-empty">暂无该项数据</p>
      </div>
    </section>

    <!-- G. 怎么参与 -->
    <section class="sec sec-participate">
      <div class="sec-title">怎么参与</div>
      <div class="sec-body">
        <p v-for="(line, i) in participateLines" :key="i" class="p-line">{{ line }}</p>
        <p v-if="!participateLines.length" class="p-empty">暂无该项数据</p>
      </div>
    </section>

    <!-- H. 后续跟踪指标 -->
    <section class="sec sec-follow">
      <div class="sec-title">后续跟踪指标</div>
      <div class="sec-body">
        <div class="follow-grid">
          <div class="follow-item">
            <div class="follow-label">费率变化</div>
            <div class="follow-value">{{ feeFollowText }}</div>
          </div>
          <div class="follow-item">
            <div class="follow-label">跟踪误差/偏离</div>
            <div class="follow-value">{{ trackingFollowText }}</div>
          </div>
          <div class="follow-item">
            <div class="follow-label">回撤承受度</div>
            <div class="follow-value">{{ drawdownFollowText }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AnalysisSection, FundAnalysisOutput, TableSection, TextSection } from '@/types/fundAnalysis'
import { firstSentence, resolveHeroConclusion } from '@/utils/fundPresentation'

const props = defineProps<{ analysis: FundAnalysisOutput }>()

function escapeRegExp(s: string): string {
  return (s || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function pickBlock(content: string, title: string): string {
  const t = (title || '').trim()
  if (!t) return ''
  const re = new RegExp(`【${escapeRegExp(t)}】\\s*([\\s\\S]*?)(?=\\n\\s*【|$)`)
  const m = content.match(re)
  return (m?.[1] || '').trim()
}

function normalizeSpace(text: string): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}

function firstTwoSentences(text: string): string {
  const clean = normalizeSpace(text || '')
  if (!clean) return ''
  const parts = clean.split(/(?<=[。！？!?])/).map((s) => s.trim()).filter(Boolean)
  return parts.slice(0, 2).join('')
}

function isPerformanceTitle(title: string): boolean {
  return /业绩表现|performance/i.test(title || '')
}

function findPerformanceSection(sections: AnalysisSection[]): TextSection | null {
  return (sections || []).find((s): s is TextSection => s.type === 'text' && isPerformanceTitle(s.title || '')) || null
}

function findStandardTable(sections: AnalysisSection[]): TableSection | null {
  const t = (sections || []).find((s): s is TableSection => s.type === 'table' && /基金详细信息/i.test(s.title || ''))
  return t || null
}

function extractStandardKv(sections: AnalysisSection[]): Record<string, string> {
  const table = findStandardTable(sections)
  if (!table?.table?.rows?.length) return {}
  const out: Record<string, string> = {}
  for (const row of table.table.rows) {
    if (!row || typeof row !== 'object') continue
    const k = String((row as Record<string, unknown>)['字段'] ?? '').trim()
    const v = String((row as Record<string, unknown>)['内容'] ?? '').trim()
    if (!k) continue
    if (v) out[k] = v
  }
  return out
}

function parseStructuredPerfRows(content: string): Array<{
  period: string
  ret: string
  rank: string
  drawdown: string
}> {
  const text = content || ''
  const start = text.indexOf('【结构化业绩数据】')
  const end = text.indexOf('---')
  if (start === -1 || end === -1 || end <= start) return []
  const block = text.slice(start, end)
  const lines = block
    .split('\n')
    .map((s) => s.trim())
    .filter((s) => s && s !== '【结构化业绩数据】')

  const pick = (line: string, patterns: RegExp[]): string => {
    for (const p of patterns) {
      const m = line.match(p)
      if (m?.[1]) return m[1].trim()
    }
    return ''
  }

  const parseRankSimple = (line: string): string => {
    const m = line.match(/同类排名[：:\s]*(\d+\s*\/\s*\d+)/)
    return (m?.[1] || '').replace(/\s+/g, '')
  }

  return lines
    .map((line) => {
      const period = (line.match(/^(成立以来|今年以来|近1月|近3月|近6月|近1年|近2年|近3年|近5年|20\d{2}年)/) || [])[1] || ''
      const ret = pick(line, [
        /收益率[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
        /收益[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
      ])
      const rank = parseRankSimple(line)
      const drawdown = pick(line, [/最大回撤(?:率)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/])
      return { period, ret, rank, drawdown }
    })
    .filter((r) => !!r.period)
}

function parseRankToPercent(rank: string): string {
  const m = rank.match(/^(\d+)\s*\/\s*(\d+)$/)
  if (!m) return ''
  const r = Number(m[1])
  const t = Number(m[2])
  if (!r || !t) return ''
  const pct = ((r / t) * 100).toFixed(1)
  return `同类前${pct}%`
}

function extractMaxDrawdown(content: string): string | null {
  const text = content || ''
  const prefer = [
    /近1年[^\n，。；]*最大回撤(?:率)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
    /近3年[^\n，。；]*最大回撤(?:率)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
    /成立以来[^\n，。；]*最大回撤(?:率)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
  ]
  for (const p of prefer) {
    const m = text.match(p)
    if (m?.[1]) return m[1]
  }
  const any = text.match(/最大回撤(?:率)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/)
  return any?.[1] || null
}

function extractTrackingMetrics(content: string): { trackingError: string | null; trackingDeviation: string | null } {
  const text = content || ''
  const te = text.match(/跟踪误差[：:\s]*([+-]?\d+(?:\.\d+)?%?)/i)?.[1] || null
  const td = text.match(/跟踪偏离(?:度)?[：:\s]*([+-]?\d+(?:\.\d+)?%?)/i)?.[1] || null
  return { trackingError: te, trackingDeviation: td }
}

function firstPercentNumber(text: string): number | null {
  const m = (text || '').match(/(\d+(?:\.\d+)?)%/)
  if (!m?.[1]) return null
  const v = Number(m[1])
  return Number.isFinite(v) ? v : null
}

const sections = computed(() => props.analysis.sections || [])
const perfSection = computed(() => findPerformanceSection(sections.value))
const perfContent = computed(() => perfSection.value?.content || '')

const standardKv = computed(() => extractStandardKv(sections.value))

const fundType = computed(() => standardKv.value['基金类型'] || '')
const trackingTarget = computed(() => standardKv.value['跟踪标的'] || standardKv.value['业绩比较基准'] || '')
const feeText = computed(() => {
  const v = standardKv.value['费率']
  return v ? v : '暂无该项数据'
})
const scaleText = computed(() => {
  const v = standardKv.value['最新规模']
  return v ? v : '暂无该项数据'
})

const isEtfLianJie = computed(() => /ETF.*联接|联接.*ETF|ETF联接|ETF聯接/i.test(fundType.value))

const retRank1y = computed(() => {
  const rows = parseStructuredPerfRows(perfContent.value)
  const row = rows.find((r) => r.period === '近1年')
  if (!row?.ret && !row?.rank) return null
  if (row.ret && row.rank) return `${row.ret}，${parseRankToPercent(row.rank)}`
  if (row.ret) return `${row.ret}，暂无该项数据`
  return null
})

const retRank3y = computed(() => {
  const rows = parseStructuredPerfRows(perfContent.value)
  const row = rows.find((r) => r.period === '近3年')
  if (!row?.ret && !row?.rank) return null
  if (row.ret && row.rank) return `${row.ret}，${parseRankToPercent(row.rank)}`
  if (row.ret) return `${row.ret}，暂无该项数据`
  return null
})

const maxDrawdownText = computed(() => {
  const v = extractMaxDrawdown(perfContent.value)
  return v ? v : '暂无该项数据'
})

const trackingMetrics = computed(() => extractTrackingMetrics(perfContent.value))

const trackingErrorText = computed(() => {
  return trackingMetrics.value.trackingError ? trackingMetrics.value.trackingError : '暂无该项数据'
})
const trackingDeviationText = computed(() => {
  return trackingMetrics.value.trackingDeviation ? trackingMetrics.value.trackingDeviation : '暂无该项数据'
})

const conclusion = computed(() => {
  const target = normalizeSpace(trackingTarget.value)
  const fee = standardKv.value['费率'] || ''
  const costPct = firstPercentNumber(fee)
  const feeWord = costPct !== null ? (costPct <= 0.5 ? '低费率' : '成本可控') : '成本可控'

  const defaultFallback = resolveHeroConclusion(props.analysis.summary, props.analysis.sections || [])
  const fallbackOne = firstSentence(defaultFallback)
  if (!isEtfLianJie.value) return fallbackOne || '暂无该项数据'

  // ETF联接重点：工具属性 + 定投 vs 短线差异（不引用具体业绩数值）
  const idx = target || '跟踪指数'
  return `这是一只${feeWord}、长期持有型的${idx}场外配置工具，适合3年以上定投获取指数Beta，不适合短线博反弹和低波动诉求。`
})

const fitText = computed(() => {
  if (isEtfLianJie.value) return '更适合3年以上、用定投平滑指数波动的投资者。'
  const fit = pickBlock(perfContent.value, '适合人群')
  return fit ? firstTwoSentences(fit) : '暂无该项数据'
})

const unfitText = computed(() => {
  if (isEtfLianJie.value) return '不适合短期用钱、或对回撤容忍度非常低的投资者。'
  const v = pickBlock(perfContent.value, '不适合人群')
  return v ? firstTwoSentences(v) : '暂无该项数据'
})

const whyLines = computed(() => {
  // 优先使用后端块内容，但保证短句拆分，避免百科式长段。
  if (!perfContent.value) return []

  const adv = pickBlock(perfContent.value, '优势')
  if (adv) {
    return firstTwoSentences(adv)
      .split('。')
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 3)
      .map((s) => s.endsWith('。') ? s : `${s}。`)
  }

  if (isEtfLianJie.value) {
    const idx = normalizeSpace(trackingTarget.value) || '跟踪指数'
    return [
      `它的目标是跟踪${idx}的收益来源。`,
      '持有越久越能把短期波动摊平。',
      '不依赖择时，适合用定投做资产配置工具。',
    ]
  }
  return []
})

const riskLines = computed(() => {
  const r = pickBlock(perfContent.value, '风险点')
  if (r) {
    return firstTwoSentences(r)
      .split('。')
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 3)
      .map((s) => (s.endsWith('。') ? s : `${s}。`))
  }

  if (isEtfLianJie.value) {
    return [
      '指数下跌时，净值也会随之回撤。',
      '存在跟踪误差与阶段性偏离风险。',
      '短线使用需要承担不确定的回撤深度。',
    ]
  }
  return []
})

const compareLines = computed(() => {
  // 如果后端没有“替代品比较”块，则用 ETF联接通用差异解释兜底（不涉及具体业绩数值）。
  if (isEtfLianJie.value) {
    return [
      '场内ETF：可以在二级市场实时交易，更适合短线与灵活换手。',
      'ETF联接：主要走场外申赎，适合定投与长期持有。',
      '不同跟踪指数（如沪深300/中证1000/同类联接）：风险风格不同，Beta并不等价。',
    ]
  }
  return []
})

const participateLines = computed(() => {
  if (isEtfLianJie.value) {
    return [
      '定投：从3年以上周期出发，分散买入节奏。',
      '短线：不建议用来博反弹，回撤与偏离可能让体验不达预期。',
    ]
  }
  // 兜底：尝试读取“怎么参与”块
  const p = pickBlock(perfContent.value, '怎么参与')
  return p ? p.split('。').map((s) => s.trim()).filter(Boolean).slice(0, 3) : []
})

const feeFollowText = computed(() => {
  // 费率通常在首屏卡片已给出，这里只给“提醒”。
  return feeText.value !== '暂无该项数据' ? '关注后续管理/托管费率调整。' : '暂无该项数据'
})

const trackingFollowText = computed(() => {
  const te = trackingMetrics.value.trackingError
  const td = trackingMetrics.value.trackingDeviation
  if (te || td) return `跟踪误差${te ? te : '暂无该项数据'}，跟踪偏离${td ? td : '暂无该项数据'}`.replace('暂无该项数据暂无该项数据', '暂无该项数据')
  return '跟踪误差/偏离：暂无该项数据'
})

const drawdownFollowText = computed(() => {
  return maxDrawdownText.value !== '暂无该项数据' ? `把最大回撤纳入资金计划（当前最大回撤：${maxDrawdownText.value}）。` : '最大回撤：暂无该项数据'
})

const ret1yText = computed(() => (retRank1y.value ? retRank1y.value : '暂无该项数据'))
const ret3yText = computed(() => (retRank3y.value ? retRank3y.value : '暂无该项数据'))
</script>

<style scoped>
.assist-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 8px 0;
}

.sec {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 16px;
}

.sec-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 10px;
}

.sec-body {
  font-size: 14px;
  color: #0f172a;
  line-height: 1.8;
}

.sec-conclusion .sec-body {
  font-weight: 700;
  font-size: 16px;
}

.aud-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.aud-block {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
}

.aud-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 700;
  margin-bottom: 6px;
}

.aud-text {
  font-size: 14px;
  color: #0f172a;
  line-height: 1.7;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}

.metric-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 700;
  margin-bottom: 6px;
}

.metric-value {
  font-size: 14px;
  color: #0f172a;
  font-weight: 600;
  line-height: 1.6;
  word-break: break-word;
}

.p-line {
  margin: 0 0 6px 0;
}

.p-empty {
  color: #64748b;
}

.follow-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.follow-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
}

.follow-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 700;
  margin-bottom: 6px;
}

.follow-value {
  font-size: 14px;
  color: #0f172a;
  font-weight: 600;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .aud-row {
    grid-template-columns: 1fr;
  }
}
</style>

