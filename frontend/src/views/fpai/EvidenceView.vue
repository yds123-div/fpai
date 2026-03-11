<template>
  <div class="evidence-view">
    <a-typography-title :level="4">证据查询</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="inline" @finish="onQuery">
        <a-form-item label="回答 ID" name="answerId" :rules="[{ required: true, message: '请输入 answerId' }]">
          <a-input v-model:value="answerId" placeholder="来自对话或对比/推荐等接口的 answerId" style="width: 280px" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading">查询证据</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-card v-if="evidence" size="small" title="证据详情">
      <a-descriptions bordered size="small" :column="1">
        <a-descriptions-item v-if="evidence.requestSummary" label="请求摘要">{{ evidence.requestSummary }}</a-descriptions-item>
        <a-descriptions-item v-if="evidence.intent" label="意图">{{ evidence.intent }}</a-descriptions-item>
        <a-descriptions-item v-if="evidence.dataSource" label="数据源">{{ evidence.dataSource }}</a-descriptions-item>
        <a-descriptions-item v-if="evidence.evidenceSnippets?.length" label="证据片段">
          <pre>{{ evidence.evidenceSnippets.join('\n') }}</pre>
        </a-descriptions-item>
        <a-descriptions-item v-if="evidence.timestamp" label="时间戳">{{ evidence.timestamp }}</a-descriptions-item>
      </a-descriptions>
      <template v-if="!evidence.requestSummary && !evidence.intent && !evidence.dataSource && !evidence.evidenceSnippets?.length">
        <a-typography-paragraph type="secondary">无结构化字段，原始数据：</a-typography-paragraph>
        <pre>{{ JSON.stringify(evidence, null, 2) }}</pre>
      </template>
    </a-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getEvidence } from '@/api/evidence'

const route = useRoute()
const answerId = ref(route.query.answerId || '')
const loading = ref(false)
const errorMsg = ref('')
const evidence = ref(null)

onMounted(() => {
  if (answerId.value) onQuery()
})

async function onQuery() {
  if (!answerId.value?.trim()) return
  errorMsg.value = ''
  evidence.value = null
  loading.value = true
  try {
    evidence.value = await getEvidence(answerId.value.trim())
  } catch (e) {
    errorMsg.value = e?.message || '获取证据失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.evidence-view {
  margin: 32px;
  padding: 32px;
}
pre {
  margin: 0;
  white-space: pre-wrap;
  font-size: 12px;
}
</style>
