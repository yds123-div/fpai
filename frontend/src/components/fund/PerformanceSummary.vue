<template>
  <div class="perf-summary">
    <div class="metric-grid">
      <div v-for="m in metrics" :key="m.label" class="metric-card">
        <div class="metric-label">{{ m.label }}</div>
        <div class="metric-value">{{ m.value || '-' }}</div>
      </div>
    </div>
    <div v-if="riskPeriodOptions.length > 1" class="risk-switches">
      <button
        v-for="period in riskPeriodOptions"
        :key="period"
        class="risk-switch-btn"
        :class="{ active: riskPeriod === period }"
        @click="riskPeriod = period"
      >
        {{ period }}
      </button>
    </div>
    <div class="ytd-card">
      <div class="block-title">今年收益与排行</div>
      <div class="ytd-row">
        <span class="k">今年以来收益</span>
        <span class="v">{{ ytdPerf.ret || '-' }}</span>
      </div>
      <div class="ytd-row">
        <span class="k">今年以来排名</span>
        <span class="v">{{ rankToPctDisplay(ytdPerf.rank) || '-' }}</span>
      </div>
    </div>
    <div class="table-card">
      <div class="block-title">分阶段收益与排行</div>
      <table class="perf-table">
        <thead>
          <tr>
            <th>阶段</th>
            <th>收益</th>
            <th>排名</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in periodRows" :key="r.period">
            <td>{{ r.period }}</td>
            <td>{{ r.ret || '-' }}</td>
            <td>{{ rankToPctDisplay(r.rank) || '-' }}</td>
          </tr>
          <tr v-if="!periodRows.length">
            <td colspan="3">暂无分阶段收益数据</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="table-card">
      <div class="block-title">历年收益与排行</div>
      <table class="perf-table">
        <thead>
          <tr>
            <th>年份</th>
            <th>收益</th>
            <th>排名</th>
            <th>最大回撤</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in yearPerfRows" :key="r.year">
            <td>{{ r.year }}</td>
            <td>{{ r.ret || '-' }}</td>
            <td>{{ rankToPctDisplay(r.rank) || '-' }}</td>
            <td>{{ r.drawdown || '-' }}</td>
          </tr>
          <tr v-if="!yearPerfRows.length">
            <td colspan="4">暂无历年收益数据</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="rankMeta" class="rank-visual-card">
      <div class="rank-head">
        <span class="rank-title">
          同类排名可视化
          <span v-if="rankMeta.period" class="rank-period-label">（{{ rankMeta.period }}）</span>
        </span>
        <span class="rank-tag" :class="rankTagClass">{{ rankMeta.display }}</span>
      </div>
      <div v-if="rankPeriodOptions.length > 1" class="rank-switches">
        <button
          v-for="period in rankPeriodOptions"
          :key="period"
          class="rank-switch-btn"
          :class="{ active: rankPeriod === period }"
          @click="rankPeriod = period"
        >
          {{ period }}
        </button>
      </div>
      <div class="rank-bar">
        <div class="rank-fill" :style="{ width: rankMeta.barWidth }" />
      </div>
      <div class="rank-foot">{{ rankMeta.rank }}/{{ rankMeta.total }}（数值越小越靠前）</div>
    </div>
    <div class="analysis-card">
      <div class="block-title">业绩表现分析</div>
      <div class="analysis-text">{{ analysisText }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TextSection } from '@/types/fundAnalysis'

interface MetricItem {
  label: string
  value: string
}

interface YearPerfRow {
  year: string
  ret: string
  rank: string
  drawdown: string
}

interface PeriodPerfRow {
  period: string
  ret: string
  rank: string
}

const props = defineProps<{ section: TextSection }>()
const STRUCTURED_PERF_DELIM = '---'

interface StructuredPerfRow {
  period: string
  ret: string
  rank: string
  drawdown: string
  sharpe: string
  volatility: string
}

interface RankPeriodOption {
  period: '近1年' | '今年以来' | '近3年' | '成立以来'
  rank: string
}

function pick(text: string, patterns: RegExp[]): string {
  for (const p of patterns) {
    const m = text.match(p)
    if (m?.[1]) return m[1].trim()
  }
  return ''
}

function parseRank(rankText: string): { total: number; rank: number; pct: number; display: string; period?: string } | null {
  const finish = (r: number, t: number) => {
    if (!t || !r) return null
    const pct = ((r / t) * 100).toFixed(1)
    return { total: t, rank: r, pct: Number(pct), display: `同类前${pct}%` }
  }
  // 优先：结构化行「近1年/今年以来/近3年/成立以来…同类排名：a/b」
  let m = rankText.match(/近1年[^\n]*?同类排名[：:\s]*(\d+)\s*\/\s*(\d+)/)
  if (m) return finish(Number(m[1]), Number(m[2]))
  m = rankText.match(/今年以来[^\n]*?同类排名[：:\s]*(\d+)\s*\/\s*(\d+)/)
  if (m) return finish(Number(m[1]), Number(m[2]))
  m = rankText.match(/近3年[^\n]*?同类排名[：:\s]*(\d+)\s*\/\s*(\d+)/)
  if (m) return finish(Number(m[1]), Number(m[2]))
  m = rankText.match(/成立以来[^\n]*?同类排名[：:\s]*(\d+)\s*\/\s*(\d+)/)
  if (m) return finish(Number(m[1]), Number(m[2]))
  // 兼容多种文案：
  // 1) 在同类4529只基金中排名第3543位
  // 2) 同类排名3543/4529
  // 3) 排名3543/4529
  // 4) 排名靠后（4326/5283）
  const patterns: RegExp[] = [
    /在同类\s*(\d+)\s*只基金中排名第\s*(\d+)\s*位/,
    /在同期\s*(\d+)\s*只基金中排名第\s*(\d+)\s*位/,
    /同类排名\s*(\d+)\s*\/\s*(\d+)/,
    /同类排名约\s*(\d+)\s*\/\s*(\d+)/,
    /排名\s*(\d+)\s*\/\s*(\d+)/,
  ]
  let rank = 0
  let total = 0
  for (const p of patterns) {
    const mm = rankText.match(p)
    if (!mm) continue
    // 「在同类/在同期 N 只…第 M 位」捕获组顺序为总数、名次；其余为 名次/总数
    if (p === patterns[0] || p === patterns[1]) {
      total = Number(mm[1])
      rank = Number(mm[2])
    } else {
      rank = Number(mm[1])
      total = Number(mm[2])
    }
    if (rank > 0 && total > 0) break
  }
  if (total && rank) return finish(rank, total)
  m = rankText.match(/排名靠后[（(]\s*(\d+)\s*\/\s*(\d+)\s*[）)]/)
  if (m) return finish(Number(m[1]), Number(m[2]))
  return null
}

function parseStructuredPerfRows(content: string): StructuredPerfRow[] {
  const text = content || ''
  const start = text.indexOf('【结构化业绩数据】')
  const end = text.indexOf(STRUCTURED_PERF_DELIM)
  if (start === -1 || end === -1 || end <= start) return []
  const block = text.slice(start, end)
  const lines = block
    .split('\n')
    .map((s) => s.trim())
    .filter((s) => s && s !== '【结构化业绩数据】')
  return lines.map((line) => {
    const period = (line.match(/^(成立以来|今年以来|近1月|近3月|近6月|近1年|近2年|近3年|近5年|20\d{2}年)/) || [])[1] || ''
    const ret = pick(line, [/收益率[：:\s]*([+-]?\d+(?:\.\d+)?%)/, /收益[：:\s]*([+-]?\d+(?:\.\d+)?%)/])
    const rank = parseRankText(line)
    const drawdown = pick(line, [/最大回撤(?:率)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/])
    const sharpe = pick(line, [/夏普比率[：:\s]*([+-]?\d+(?:\.\d+)?)/, /夏普[：:\s]*([+-]?\d+(?:\.\d+)?)/])
    const volatility = pick(line, [/年化波动率[：:\s]*([+-]?\d+(?:\.\d+)?%)/, /波动率[：:\s]*([+-]?\d+(?:\.\d+)?%)/])
    return { period, ret, rank, drawdown, sharpe, volatility }
  }).filter((r) => !!r.period)
}

function rankToPctDisplay(rank: string): string {
  if (!rank || rank === '-') return rank
  const m = rank.match(/^(\d+)\s*\/\s*(\d+)$/)
  if (!m) return rank
  const r = Number(m[1])
  const t = Number(m[2])
  if (!r || !t) return rank
  const pct = ((r / t) * 100).toFixed(1)
  return `${rank} (前${pct}%)`
}

function parseRankText(text: string): string {
  const colonRk = text.match(/同类排名[：:\s]*(\d+\s*\/\s*\d+)/)
  if (colonRk?.[1]) return colonRk[1].replace(/\s+/g, '')
  const slash = text.match(/排名\s*(\d+\s*\/\s*\d+)/)
  if (slash?.[1]) return slash[1].replace(/\s+/g, '')
  const slash2 = text.match(/同类排名约\s*(\d+\s*\/\s*\d+)/)
  if (slash2?.[1]) return slash2[1].replace(/\s+/g, '')
  const inner = text.match(/（同类排名\s*(\d+\s*\/\s*\d+)\s*）/)
  if (inner?.[1]) return inner[1].replace(/\s+/g, '')
  const full = text.match(/在同类\s*(\d+)\s*只基金中排名第\s*(\d+)\s*位/)
  if (full) return `${full[2]}/${full[1]}`
  const full2 = text.match(/在同期\s*(\d+)\s*只基金中排名第\s*(\d+)\s*位/)
  if (full2) return `${full2[2]}/${full2[1]}`
  const pct = text.match(/排名同类后\s*(\d+(?:\.\d+)?)\s*%/)
  if (pct) return `后${pct[1]}%`
  const paren = text.match(/[（(]\s*(\d+)\s*\/\s*(\d+)\s*[）)]/)
  if (paren) return `${paren[1]}/${paren[2]}`
  return ''
}

const rankMeta = computed(() => {
  const text = props.section.content || ''
  const structured = parseStructuredPerfRows(text)
  const orderedPeriods: RankPeriodOption['period'][] = ['近1年', '今年以来', '近3年', '成立以来']
  const options = orderedPeriods
    .map((period) => {
      const row = structured.find((r) => r.period === period)
      return row?.rank ? { period, rank: row.rank } : null
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)
  const active = rankPeriod.value
    ? options.find((o) => o.period === rankPeriod.value) || options[0]
    : options[0]
  if (active?.rank) {
    const m = active.rank.match(/(\d+)\s*\/\s*(\d+)/)
    if (m) {
      const rank = Number(m[1])
      const total = Number(m[2])
      const pct = Number(((rank / total) * 100).toFixed(1))
      return {
        total,
        rank,
        pct,
        display: `同类前${pct.toFixed(1)}%`,
        barWidth: `${Math.min(100, Math.max(0, pct))}%`,
        period: active.period,
      }
    }
  }
  const parsed = parseRank(text)
  if (!parsed) return null
  return {
    ...parsed,
    barWidth: `${Math.min(100, Math.max(0, parsed.pct))}%`,
  }
})

const rankPeriodOptions = computed<string[]>(() => {
  const structured = parseStructuredPerfRows(props.section.content || '')
  const orderedPeriods: RankPeriodOption['period'][] = ['近1年', '今年以来', '近3年', '成立以来']
  return orderedPeriods.filter((period) => structured.some((r) => r.period === period && !!r.rank))
})

const rankPeriod = ref<string>('')

watch(
  rankPeriodOptions,
  (opts) => {
    rankPeriod.value = opts[0] || ''
  },
  { immediate: true },
)

const rankTagClass = computed(() => {
  if (!rankMeta.value) return ''
  const pct = rankMeta.value.pct
  if (pct <= 30) return 'rank-good'
  if (pct <= 60) return 'rank-mid'
  return 'rank-weak'
})

const inceptionPerf = computed(() => {
  const text = props.section.content || ''
  const structured = parseStructuredPerfRows(text).find((r) => r.period === '成立以来')
  if (structured) {
    return { ret: structured.ret || '', rank: structured.rank || '' }
  }
  const ret = pick(text, [/成立以来[^\n，。；]*收益率?(?:为)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/])
  const rank = parseRankText((text.match(/成立以来[^\n。；]*/) || [])[0] || '')
  return { ret, rank }
})

const riskPeriod = ref('')
const riskRows = computed(() => {
  const structured = parseStructuredPerfRows(props.section.content || '')
  const periods = ['近1年', '近3年', '近5年']
  return periods
    .map((p) => {
      const r = structured.find((x) => x.period === p)
      return { period: p, sharpe: r?.sharpe || '', volatility: r?.volatility || '' }
    })
    .filter((r) => r.sharpe || r.volatility)
})
const riskPeriodOptions = computed(() => riskRows.value.map((r) => r.period))
watch(
  riskPeriodOptions,
  (opts) => {
    if (!opts.length) {
      riskPeriod.value = ''
      return
    }
    if (!riskPeriod.value || !opts.includes(riskPeriod.value)) {
      riskPeriod.value = opts[0]
    }
  },
  { immediate: true },
)
const activeRisk = computed(() => riskRows.value.find((r) => r.period === riskPeriod.value) || riskRows.value[0] || null)

const metrics = computed<MetricItem[]>(() => {
  const text = props.section.content || ''
  const inception = inceptionPerf.value
  const fallbackSharpe = pick(text, [
    /夏普比率(?:维持在|在)?[：:\s]*([+-]?\d+(?:\.\d+)?(?:\s*[-~至]\s*[+-]?\d+(?:\.\d+)?)?)/,
    /夏普(?:维持在|在)?[：:\s]*([+-]?\d+(?:\.\d+)?(?:\s*[-~至]\s*[+-]?\d+(?:\.\d+)?)?)/,
  ])
  const fallbackVolatility = pick(text, [
    /年化波动率(?:较低|较高|维持在|在)?[^\d+-]*([+-]?\d+(?:\.\d+)?%(?:\s*[-~至]\s*[+-]?\d+(?:\.\d+)?%)?)/,
    /波动率(?:较低|较高|维持在|在)?[^\d+-]*([+-]?\d+(?:\.\d+)?%(?:\s*[-~至]\s*[+-]?\d+(?:\.\d+)?%)?)/,
  ])
  const sharpe = activeRisk.value?.sharpe || fallbackSharpe
  const volatility = activeRisk.value?.volatility || fallbackVolatility
  const riskPeriodLabel = activeRisk.value?.period ? `（${activeRisk.value.period}）` : ''
  return [
    { label: '成立以来收益', value: inception.ret },
    { label: `夏普比率${riskPeriodLabel}`, value: sharpe },
    { label: `年化波动${riskPeriodLabel}`, value: volatility },
    { label: '成立以来同类排名', value: rankToPctDisplay(inception.rank) },
  ]
})

const yearPerfRows = computed<YearPerfRow[]>(() => {
  const text = props.section.content || ''
  const structured = parseStructuredPerfRows(text)
    .filter((r) => /^20\d{2}年$/.test(r.period))
    .map((r) => ({ year: r.period.slice(0, 4), ret: r.ret || '-', rank: r.rank || '-', drawdown: r.drawdown || '-' }))
  if (structured.length) return structured
  const rows: YearPerfRow[] = []
  const chunks = text.split(/(?=20\d{2}年)/).filter(Boolean)
  for (const chunk of chunks) {
    const year = (chunk.match(/(20\d{2})年/) || [])[1] || ''
    if (!year) continue
    const ret = pick(chunk, [
      /年收益率[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
      /收益(?:达|为|是)[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
      /收益(?:率)?(?:为|达|是)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
      /收益率?(?:为)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
    ])
    const rank = parseRankText(chunk)
    const drawdown = pick(chunk, [/最大回撤(?:率)?(?:为)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/])
    if (!ret && !rank && !drawdown) continue
    rows.push({ year, ret: ret || '-', rank: rank || '-', drawdown: drawdown || '-' })
  }
  return rows
})

const ytdPerf = computed(() => {
  const text = props.section.content || ''
  const structured = parseStructuredPerfRows(text).find((r) => r.period === '今年以来')
  if (structured) {
    return { ret: structured.ret || '', rank: structured.rank || '' }
  }
  const ret = pick(text, [
    /今年以来[^\n，。；]*收益率?(?:为)?[：:\s]*([+-]?\d+(?:\.\d+)?%)/,
    /今年以来收益(?:率)?[^\d+-]*([+-]?\d+(?:\.\d+)?%)/
  ])
  const rank = parseRankText((text.match(/今年以来[^\n。；]*/) || [])[0] || '')
  return { ret, rank }
})

const periodRows = computed<PeriodPerfRow[]>(() => {
  const text = props.section.content || ''
  const periods = ['近1月', '近3月', '近6月', '近1年', '近3年']
  const structuredRows = parseStructuredPerfRows(text)
  const fromStructured = periods
    .map((period) => {
      const r = structuredRows.find((x) => x.period === period)
      return { period, ret: r?.ret || '', rank: r?.rank || '' }
    })
    .filter((r) => r.ret || r.rank)
  if (fromStructured.length) return fromStructured
  return periods
    .map((period) => {
      const ret = pick(text, [
        new RegExp(`${period}收益率?(?:为)?\\s*([+-]?\\d+(?:\\.\\d+)?%)`),
        new RegExp(`${period}收益(?:率)?(?:为)?\\s*([+-]?\\d+(?:\\.\\d+)?%)`),
      ])
      const seg = (text.match(new RegExp(`${period}[^\\n。；]*`)) || [])[0] || ''
      const rank = parseRankText(seg)
      return { period, ret, rank }
    })
    .filter((r) => r.ret || r.rank)
})

const analysisText = computed(() => {
  const structuredRows = parseStructuredPerfRows(props.section.content || '')
  const points: string[] = []
  const ytd = ytdPerf.value
  const oneMonth = periodRows.value.find((r) => r.period === '近1月')
  const threeMonth = periodRows.value.find((r) => r.period === '近3月')
  const sixMonth = periodRows.value.find((r) => r.period === '近6月')
  if (ytd.ret) {
    points.push(`今年以来收益为${ytd.ret}${ytd.rank ? `，同类排名${ytd.rank}` : ''}。`)
  }
  if (oneMonth?.ret || threeMonth?.ret) {
    const shortParts = [oneMonth, threeMonth]
      .filter((r): r is PeriodPerfRow => !!r && !!r.ret)
      .map((r) => `${r.period}${r.ret}${r.rank ? `（排名${r.rank}）` : ''}`)
    if (shortParts.length) {
      points.push(`短期维度看，${shortParts.join('，')}，可用于观察最近市场环境下的弹性与回撤修复能力。`)
    }
  }
  if (sixMonth?.ret) {
    points.push(`近6月收益${sixMonth.ret}${sixMonth.rank ? `（排名${sixMonth.rank}）` : ''}，可以辅助判断近阶段持续性。`)
  }
  const oneYear = periodRows.value.find((r) => r.period === '近1年')
  if (oneYear?.ret) {
    points.push(`近1年收益${oneYear.ret}${oneYear.rank ? `（排名${oneYear.rank}）` : ''}，反映中期表现。`)
  }
  const threeYear = periodRows.value.find((r) => r.period === '近3年')
  if (threeYear?.ret) {
    points.push(`近3年收益${threeYear.ret}${threeYear.rank ? `（排名${threeYear.rank}）` : ''}，可用于评估长期稳定性。`)
  }
  const sinceInception = structuredRows.find((r) => r.period === '成立以来')
  if (sinceInception?.ret) {
    points.push(`成立以来累计收益为${sinceInception.ret}${sinceInception.rank ? `，同类排名${sinceInception.rank}` : ''}，体现了产品在更长周期中的整体回报能力。`)
  }
  const drawdownSource =
    structuredRows.find((r) => r.period === '近1年' && r.drawdown) ||
    structuredRows.find((r) => r.period === '今年以来' && r.drawdown) ||
    yearPerfRows.value.find((r) => r.drawdown && r.drawdown !== '-')
  if (drawdownSource?.drawdown) {
    const ddPeriod = 'period' in drawdownSource ? drawdownSource.period : `${drawdownSource.year}年`
    points.push(`${ddPeriod}最大回撤为${drawdownSource.drawdown}，可帮助评估产品在波动环境下的回撤控制水平。`)
  }
  if (rankMeta.value) {
    const rankTone =
      rankMeta.value.pct <= 30
        ? '处于同类靠前位置'
        : rankMeta.value.pct <= 60
          ? '处于同类中游水平'
          : '处于同类偏后位置'
    points.push(`从同类比较看，当前排名位于${rankMeta.value.rank}/${rankMeta.value.total}，${rankTone}。`)
  }
  const recentYears = yearPerfRows.value
    .filter((r) => r.ret && r.ret !== '-')
    .slice(0, 3)
    .map((r) => `${r.year}年${r.ret}${r.rank && r.rank !== '-' ? `（排名${r.rank}）` : ''}`)
  if (recentYears.length) {
    points.push(`历年表现上，${recentYears.join('，')}，便于从年度维度观察业绩稳定性与风格一致性。`)
  }
  if (!points.length) {
    return '当前文本中可提取的收益与排名信息较少，建议结合净值曲线和最大回撤等指标综合判断。'
  }
  return points.join('')
})

// instrumentation removed
</script>

<style scoped>
.perf-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.metric-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  margin-top: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.ytd-card,
.table-card,
.analysis-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
}

.ytd-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  line-height: 1.8;
}

.ytd-row .k {
  color: #64748b;
}

.ytd-row .v {
  color: #0f172a;
  font-weight: 600;
}

.perf-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.perf-table th,
.perf-table td {
  border-bottom: 1px solid #e2e8f0;
  padding: 6px 4px;
  text-align: left;
}

.perf-table thead th {
  color: #475569;
  font-weight: 600;
}

.analysis-text {
  font-size: 14px;
  line-height: 1.7;
  color: #1f2937;
}

.rank-visual-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
}

.rank-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.rank-title {
  font-size: 13px;
  color: #475569;
}

.rank-period-label {
  color: #64748b;
}

.rank-tag {
  font-size: 12px;
  font-weight: 600;
  border-radius: 999px;
  padding: 2px 10px;
}

.rank-good {
  color: #166534;
  background: #dcfce7;
}

.rank-mid {
  color: #9a3412;
  background: #ffedd5;
}

.rank-weak {
  color: #991b1b;
  background: #fee2e2;
}

.rank-bar {
  margin-top: 8px;
  height: 8px;
  width: 100%;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.rank-switches {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.risk-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rank-switch-btn {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
}

.risk-switch-btn {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
}

.rank-switch-btn.active {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #1d4ed8;
}

.risk-switch-btn.active {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #1d4ed8;
}

.rank-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #22c55e, #f59e0b, #ef4444);
}

.rank-foot {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

@media (max-width: 768px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
