<template>
  <div class="feedback-view">
    <a-typography-title :level="4">回答反馈</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="vertical" @finish="onSubmit">
        <a-form-item label="回答 ID（answerId）" name="answerId" :rules="[{ required: true, message: '请输入 answerId' }]">
          <a-input v-model:value="answerId" placeholder="来自对话或对比/推荐等接口的 answerId" allow-clear />
        </a-form-item>
        <a-form-item label="评价" name="rating" :rules="[{ required: true, message: '请选择评价' }]">
          <a-radio-group v-model:value="rating">
            <a-radio value="useful">有用</a-radio>
            <a-radio value="not_useful">无用</a-radio>
            <a-radio value="inaccurate">不准确</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="补充说明（可选）" name="comment">
          <a-textarea v-model:value="comment" placeholder="可选" :rows="2" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading">提交反馈</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-alert v-if="successMsg" type="success" :message="successMsg" show-icon style="margin-bottom: 16px" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { postFeedback } from '@/api/feedback'

const answerId = ref('')
const rating = ref('useful')
const comment = ref('')
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

async function onSubmit() {
  errorMsg.value = ''
  successMsg.value = ''
  loading.value = true
  try {
    await postFeedback({
      answerId: answerId.value?.trim(),
      rating: rating.value,
      comment: comment.value?.trim() || undefined,
    })
    successMsg.value = '反馈已提交'
  } catch (e) {
    errorMsg.value = e?.message || '反馈提交失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.feedback-view {
  margin: 32px;
  padding: 32px;
}
</style>
