<template>
  <div class="compare-view">
    <a-typography-title :level="4">产品对比</a-typography-title>
    <a-card size="small" style="margin-bottom: 16px">
      <a-form layout="vertical" @finish="onSubmit">
        <a-form-item label="产品 ID（至少 2 个，逗号分隔）" name="productIds" :rules="[{ required: true, message: '请输入至少 2 个产品 ID' }]">
          <a-input v-model:value="productIdsText" placeholder="如：p1,p2 或 p1, p2, p3" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading">生成对比</a-button>
        </a-form-item>
      </a-form>
    </a-card>
    <a-alert v-if="errorMsg" type="error" :message="errorMsg" show-icon style="margin-bottom: 16px" />
    <a-card v-if="result" size="small" title="对比结果">
      <a-typography-paragraph v-if="result.summary"><strong>差异总结：</strong>{{ result.summary }}</a-typography-paragraph>
      <a-table
        v-if="result.comparisonTable?.length"
        :columns="tableColumns"
        :data-source="tableData"
        :pagination="false"
        size="small"
        row-key="dimension"
      />
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { postCompare } from '@/api/compare'

const productIdsText = ref('')
const loading = ref(false)
const errorMsg = ref('')
const result = ref(null)

const tableColumns = computed(() => {
  if (!result.value?.comparisonTable?.length) return []
  const first = result.value.comparisonTable[0]
  const cols = [{ title: '维度', dataIndex: 'dimension', key: 'dimension', width: 120 }]
  Object.keys(first || {}).forEach((k) => {
    if (k !== 'dimension') cols.push({ title: k.replace(/^product_/, '产品 '), dataIndex: k, key: k })
  })
  return cols
})

const tableData = computed(() => {
  return (result.value?.comparisonTable || []).map((row) => ({ ...row, key: row.dimension }))
})

async function onSubmit() {
  const ids = (productIdsText.value || '').split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean)
  if (ids.length < 2) {
    errorMsg.value = '请输入至少 2 个产品 ID'
    return
  }
  errorMsg.value = ''
  result.value = null
  loading.value = true
  try {
    result.value = await postCompare({ productIds: ids })
  } catch (e) {
    errorMsg.value = e?.message || '对比请求失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.compare-view {
  margin: 32px;
  padding: 32px;
}
</style>
