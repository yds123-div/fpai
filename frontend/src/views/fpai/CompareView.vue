<template>
  <div class="compare-view">
    <a-typography-title :level="4">产品对比</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="vertical" @finish="onSubmit">
        <a-form-item label="基金代码（至少 2 个，至多 5 个）" name="productIds">
          <a-input
            v-model:value="productIdsText"
            placeholder="请输入 6 位基金代码，逗号或空格分隔，如：000001, 161725"
            allow-clear
          />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="loading" @click="onSubmit">生成对比</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-card v-if="loading || streamText" size="small" title="对比结果">
      <a-typography-paragraph v-if="loading && !streamText" type="secondary">正在生成对比，请稍候…</a-typography-paragraph>
      <a-typography-paragraph v-if="streamText" class="stream-text">{{ streamText }}</a-typography-paragraph>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { postCompareStream } from '@/api/compare'

const productIdsText = ref('')
const loading = ref(false)
const errorMsg = ref('')
const streamText = ref('')
let stopStream: null | (() => void) = null

function parseAndValidateCodes(raw: string): string[] {
  const ids = (raw || '')
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (ids.length < 2) throw new Error('请至少输入 2 个基金代码')
  if (ids.length > 5) throw new Error('最多输入 5 个基金代码')
  const invalid = ids.find((id) => !/^\d{6}$/.test(id))
  if (invalid) throw new Error(`基金代码格式错误：${invalid}（需为 6 位数字）`)
  return ids
}

async function onSubmit() {
  let ids: string[] = []
  try {
    ids = parseAndValidateCodes(productIdsText.value)
  } catch (e) {
    errorMsg.value = (e as Error)?.message || '输入参数不合法'
    return
  }
  if (stopStream) stopStream()
  errorMsg.value = ''
  streamText.value = ''
  loading.value = true
  stopStream = postCompareStream(
    { productIds: ids },
    {
      onMessage: (data) => {
        if (data?.text) streamText.value += data.text
      },
      onDone: () => {
        loading.value = false
        stopStream = null
      },
      onError: (e) => {
        errorMsg.value = e?.message || '对比请求失败'
        loading.value = false
        stopStream = null
      },
    }
  )
}
</script>

<style scoped>
.compare-view {
  margin: 32px;
  padding: 32px;
}

.stream-text {
  white-space: pre-wrap;
  margin-bottom: 0;
}
</style>
