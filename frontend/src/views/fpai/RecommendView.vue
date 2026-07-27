<template>
  <div class="recommend-view">
    <a-typography-title :level="4">产品推荐</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="vertical">
        <a-form-item label="客户画像 / 需求描述" name="customerProfile" >
          <a-textarea v-model:value="customerProfile" placeholder="如：稳健型、期限 1 年、可接受中低风险" :rows="3" allow-clear />
        </a-form-item>
        <a-form-item label="客户画像示例">
          <a-select
            v-model:value="selectedProfileExampleId"
            :options="customerProfileExampleOptions"
            placeholder="选择一个示例（可自动填充）"
            allow-clear
            style="width: 300px"
          />
        </a-form-item>
        <a-form-item label="推荐条数" name="topN">
          <a-input-number v-model:value="topN" :min="1" :max="10" style="width: 120px" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="button" :loading="loading" @click="onSubmit">获取推荐</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-card v-if="result" size="small" title="推荐结果">
      <a-typography-paragraph v-if="result.disclaimers" type="secondary">{{ result.disclaimers }}</a-typography-paragraph>
      <a-list :data-source="result.products || []" item-layout="vertical">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="item.name || item.id" />
            <template #actions>
              <span v-if="item.reason">推荐理由：{{ item.reason }}</span>
            </template>
          </a-list-item>
        </template>
      </a-list>
      <a-typography-paragraph v-if="(result.products || []).length === 0 && streamText" class="stream-text">{{ streamText }}</a-typography-paragraph>
    </a-card>
    <a-card v-else-if="loading || streamText" size="small" title="推荐结果">
      <a-typography-paragraph v-if="loading && !streamText" type="secondary">正在生成推荐，请稍候…</a-typography-paragraph>
      <a-typography-paragraph v-if="streamText" class="stream-text">{{ streamText }}</a-typography-paragraph>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { postRecommendStream } from '@/api/recommend'

type RecommendedProduct = {
  id?: string
  name?: string
  reason?: string
  tags?: string
}

type RecommendParseResult = {
  disclaimers: string
  products: RecommendedProduct[]
}

const customerProfile = ref('')
const selectedProfileExampleId = ref<string | null>(null)
const customerProfileExamples = ref<{ id: string; label: string; text: string }[]>([
  {
    id: 'example_stable_hnw_female_40',
    label: '示例：稳健型高净值（40岁女）',
    text:
      '该客户是稳健型高净值客户，具有保守型投资偏好。40岁女性，职业为财务总监，资产规模达四星级（近一年日均金融资产57万元）。财务状况良好，收入水平高，资产配置以稳健型产品为主（理财占比52.7%，债券型基金占比21.4%）。风险承受能力较低，明确偏好保守型投资策略。主要关注资产保值需求，对收益波动敏感。建议重点配置低风险理财产品和优质债券基金，可适当搭配少量混合型基金（当前占比14.5%）以优化收益。需特别注意产品安全性和流动性，定期提供资产配置检视服务。',
  },
  {
    id: 'example_growth_hnw_male_30',
    label: '示例：高净值进取（30岁男）',
    text:
      '该客户是高净值进取型投资者，30岁男性，职业为投资经理，资产规模达150万元。财务状况优异，收入水平高，资产配置以股票型基金（84.01万元）为主，辅以混合型（41.30万元）和债券型基金（20.34万元），显示其偏好成长型产品。风险偏好为进取型，投资经验丰富且交易活跃（近6个月基金交易20次）。主要关注高收益成长类资产，建议重点提供定制化权益类产品组合、市场动态分析及高端投资渠道，同时关注其资产流动性需求以优化配置结构。',
  },
  {
    id: 'example_uhnw_private_banking_37',
    label: '示例：超高净值企业主（37岁）',
    text:
      '该客户是超高净值企业主，37岁，资产规模达私人银行级别，日均金融资产1亿元。财务状况优异，收入水平高，资产配置多元化，涵盖理财、股票型基金、债券型基金和混合型基金，投资经验丰富（10年）。风险偏好待重新评估（原记录为“其他”），但交易活跃（近6个月理财25次、基金30次），显示较高风险承受潜力。主要需求为资产保值增值与多元化配置，需关注风险评估更新以精准匹配产品。建议重点提供定制化财富管理方案，强化税务规划与跨境资产配置服务，同时定期检视风险偏好动态调整投资组合。',
  },
])

const customerProfileExampleOptions = customerProfileExamples.value.map((x) => ({ value: x.id, label: x.label }))

function applySelectedExample(id: string | null) {
  if (!id) return
  const ex = customerProfileExamples.value.find((x) => x.id === id)
  if (ex) customerProfile.value = ex.text
}

// 选择示例后自动填充到输入框
applySelectedExample(selectedProfileExampleId.value)

// 使用 v-model 时监听变化更稳（避免 select 内部触发顺序差异）
watch(selectedProfileExampleId, (n) => applySelectedExample(n))

const topN = ref(5)
const loading = ref(false)
const errorMsg = ref('')
const result = ref<RecommendParseResult | null>(null)
const streamText = ref('')
// postRecommendStream 返回用于停止流式推送的句柄/回调（此处先显式标注避免 TS 推导成 null 或 any）
let stopStream: any = null

function parseRecommendText(text: string): RecommendParseResult {
  const disclaimers: string = '基金有风险，投资需谨慎。以上内容由AI生成，仅供参考，不构成投资建议。'
  if (!text) return { disclaimers, products: [] }

  const lines = String(text)
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean)

  const headerRe = /^(\d+)\.\s*(.+?)（(.+?)）\s*$/
  const products: RecommendedProduct[] = []
  let cur: RecommendedProduct | null = null
  let collectingReason = false

  const flush = () => {
    if (cur) products.push(cur)
    cur = null
    collectingReason = false
  }

  for (const ln of lines) {
    const m = ln.match(headerRe)
    if (m) {
      flush()
      cur = { name: (m[2] || '').trim(), id: (m[3] || '').trim(), reason: '', tags: '' }
      collectingReason = false
      continue
    }
    if (!cur) continue

    if (ln.startsWith('推荐原因：') || ln.startsWith('推荐原因:')) {
      collectingReason = true
      cur.reason = ln.replace(/^推荐原因[：:]/, '').trim()
      continue
    }

    if (collectingReason) {
      if (ln.startsWith('适配标签：') || ln.startsWith('适配标签:')) {
        collectingReason = false
        cur.tags = ln.replace(/^适配标签[：:]/, '').trim()
        continue
      }
      cur.reason = cur.reason ? `${cur.reason}${ln}` : ln
      continue
    }

    if (ln.startsWith('适配标签：') || ln.startsWith('适配标签:')) {
      cur.tags = ln.replace(/^适配标签[：:]/, '').trim()
      continue
    }
  }

  flush()
  return { disclaimers, products }
}

async function onSubmit() {
  errorMsg.value = ''
  result.value = null
  streamText.value = ''
  loading.value = true
  if (stopStream) stopStream()
  try {
    stopStream = postRecommendStream(
      {
        customerProfile: customerProfile.value?.trim() || {},
        topN: topN.value,
      },
      {
        onMessage: (data) => {
          if (data?.text) streamText.value += data.text
        },
        onDone: () => {
          loading.value = false
          stopStream = null
          result.value = parseRecommendText(streamText.value)
        },
        onError: (e) => {
          errorMsg.value = e?.message || '推荐请求失败'
          loading.value = false
          stopStream = null
        },
      }
    )
  } catch (e: any) {
    errorMsg.value = e?.message || '推荐请求失败'
    loading.value = false
  } finally {
    // SSE 由 onDone/onError 结束 loading
  }
}
</script>

<style scoped>
.recommend-view {
  margin: 32px;
  padding: 32px;
}

.stream-text {
  white-space: pre-wrap;
  margin-bottom: 0;
}
</style>
