<template>
  <div class="recommend-view">
    <a-typography-title :level="4">产品推荐</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="vertical" @finish="onSubmit">
        <a-form-item label="客户画像 / 需求描述" name="customerProfile" :rules="[{ required: true, message: '请填写客户画像或需求' }]">
          <a-textarea v-model:value="customerProfile" placeholder="如：稳健型、期限 1 年、可接受中低风险" :rows="3" allow-clear />
        </a-form-item>
        <a-form-item label="推荐条数" name="topN">
          <a-input-number v-model:value="topN" :min="1" :max="20" style="width: 120px" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading">获取推荐</a-button>
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
    </a-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { postRecommend } from '@/api/recommend'

const customerProfile = ref('')
const topN = ref(5)
const loading = ref(false)
const errorMsg = ref('')
const result = ref(null)

async function onSubmit() {
  errorMsg.value = ''
  result.value = null
  loading.value = true
  try {
    result.value = await postRecommend({
      customerProfile: customerProfile.value?.trim() || {},
      topN: topN.value,
    })
  } catch (e) {
    errorMsg.value = e?.message || '推荐请求失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.recommend-view {
  margin: 32px;
  padding: 32px;
}
</style>
