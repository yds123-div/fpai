<template>
  <div class="info-card" :class="`card-${card.type}`">
    <div class="card-header">{{ displayTitle }}</div>
    <div class="card-body">
      <template v-if="useTableLayout">
        <table class="kv-table" role="table" aria-label="基本信息表格">
          <tbody>
            <tr v-for="row in tableRows" :key="row.key" class="kv-row">
              <th class="kv-key" scope="row">{{ row.label }}</th>
              <td class="kv-val" :class="valueClass(row.key, row.value)">{{ row.value }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <template v-else>
        <div v-for="(value, key) in displayData" :key="key" class="card-item">
          <span class="item-label">{{ formatLabel(String(key)) }}</span>
          <span class="item-value" :class="valueClass(String(key), value)">{{ value }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { InfoCard } from '@/types/fundAnalysis'

const props = defineProps<{ card: InfoCard }>()

const LABEL_MAP: Record<string, string> = {
  code: '基金代码',
  name: '基金名称',
  type: '基金类型',
  manager: '基金经理',
  scale: '基金规模',
  riskLevel: '风险等级',
  establishDate: '成立日期',
  purchaseStatus: '申购状态',
  redeemStatus: '赎回状态',
  status: '状态',
  managementFee: '管理费',
  custodyFee: '托管费',
  subscriptionFee: '申购费',
  redemptionFee: '赎回费',
  salesServiceFee: '销售服务费',
  return_1m: '近1月',
  return_6m: '近6月',
  return_1y: '近1年',
  return_3y: '近3年',
  return_ytd: '今年以来',
  return_since_inception: '成立以来',
  sharpe: '夏普比率',
  maxDrawdown: '最大回撤',
  volatility: '波动率'
}

function formatLabel(key: string): string {
  return LABEL_MAP[key] || key
}

function valueClass(key: string, val: unknown): string {
  const s = String(val || '')
  if (key.startsWith('return_') || key === 'return_ytd') {
    if (s.startsWith('+') || (s.match(/^[\d.]/) && !s.startsWith('-') && !s.startsWith('0'))) return 'val-positive'
    if (s.startsWith('-')) return 'val-negative'
  }
  if (key === 'maxDrawdown' && s.startsWith('-')) return 'val-negative'
  return ''
}

const displayData = computed(() => {
  if (!props.card.data) return {}
  return props.card.data
})

function isBasicInfoCard(card: InfoCard): boolean {
  const title = String(card.title || '')
  return card.type === 'basic' || /基本信息|basic/i.test(title)
}

const useTableLayout = computed(() => isBasicInfoCard(props.card))

const TABLE_ORDER = [
  'code',
  'name',
  'type',
  'manager',
  'scale',
  'riskLevel',
  'establishDate',
  'purchaseStatus',
  'redeemStatus',
  'status',
  'managementFee',
  'custodyFee',
  'subscriptionFee',
  'redemptionFee',
  'salesServiceFee'
]

const tableRows = computed(() => {
  const obj = displayData.value as Record<string, unknown>
  const keys = Object.keys(obj || {})
  const ordered = [
    ...TABLE_ORDER.filter((k) => keys.includes(k)),
    ...keys.filter((k) => !TABLE_ORDER.includes(k))
  ]
  const rows = ordered
    .map((k) => ({
      key: k,
      label: formatLabel(k),
      value: String(obj?.[k] ?? '')
    }))
    .filter((r) => r.value !== '')

  return rows
})

const displayTitle = computed(() => {
  const title = String(props.card.title || '')
  const code = String((props.card.data?.code as string) || '')
  const name = String((props.card.data?.name as string) || '')

  // Compare mode often returns two cards with the same "基本信息" title.
  // Add a short identity suffix to avoid looking duplicated.
  if (/基本信息|basic/i.test(title)) {
    if (code) return `${title}（${code}）`
    if (name) return `${title}（${name}）`
  }
  return title
})
</script>

<style scoped>
.info-card {
  background: var(--card-bg, #fff);
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-left: 4px solid #d9d9d9;
  transition: box-shadow 0.2s;
}

.info-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.card-basic {
  border-left-color: #5470c6;
}

.card-performance {
  border-left-color: #91cc75;
}

.card-risk {
  border-left-color: #ee6666;
}

.card-fee {
  border-left-color: #fac858;
}

.card-header {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary, #1a1a1a);
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.kv-row + .kv-row .kv-key,
.kv-row + .kv-row .kv-val {
  border-top: 1px solid var(--border-light, #f0f0f0);
}

.kv-key {
  text-align: left;
  color: var(--text-secondary, #666);
  font-weight: 500;
  padding: 6px 10px 6px 0;
  vertical-align: top;
  width: 38%;
}

.kv-val {
  text-align: right;
  color: var(--text-primary, #333);
  font-weight: 500;
  padding: 6px 0 6px 10px;
  vertical-align: top;
  word-break: break-all;
}

.card-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid var(--border-light, #f0f0f0);
  font-size: 13px;
}

.card-item:last-child {
  border-bottom: none;
}

.item-label {
  color: var(--text-secondary, #666);
  flex-shrink: 0;
  margin-right: 12px;
}

.item-value {
  color: var(--text-primary, #333);
  font-weight: 500;
  text-align: right;
  word-break: break-all;
}

.val-positive {
  color: #cf1322;
}

.val-negative {
  color: #3f8600;
}
</style>
