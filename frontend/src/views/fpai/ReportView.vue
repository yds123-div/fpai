<template>
  <div class="report-view">
    <a-typography-title :level="4">报告生成</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="vertical" @finish="onSubmit">
        <a-form-item label="模板/类型" name="templateId">
          <a-input v-model:value="templateId" placeholder="如：周报、月报、市场解读" allow-clear />
        </a-form-item>
        <a-form-item label="时间范围" name="timeRange">
          <a-input v-model:value="timeRange" placeholder="如：本周、本月" allow-clear />
        </a-form-item>
        <a-form-item label="主题（可选）" name="topic">
          <a-input v-model:value="topic" placeholder="如：市场解读" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading">生成报告</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-card v-if="result" size="small" title="报告内容">
      <div v-for="(block, i) in (result.reportBlocks || [])" :key="i" class="report-block">
        <a-typography-title v-if="block.type" :level="5">{{ block.type }}</a-typography-title>
        <a-typography-paragraph>{{ block.content || block }}</a-typography-paragraph>
      </div>
    </a-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { postReportGenerate } from '@/api/report'

const templateId = ref('周报')
const timeRange = ref('本周')
const topic = ref('')
const loading = ref(false)
const errorMsg = ref('')
const result = ref(null)

async function onSubmit() {
  errorMsg.value = ''
  result.value = null
  loading.value = true
  try {
    result.value = await postReportGenerate({
      templateId: templateId.value?.trim() || undefined,
      timeRange: timeRange.value?.trim() || undefined,
      topic: topic.value?.trim() || undefined,
    })
  } catch (e) {
    errorMsg.value = e?.message || '报告生成失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.report-view {
  margin: 32px;
  padding: 32px;
}
.report-block {
  margin-bottom: 16px;
}
</style>
