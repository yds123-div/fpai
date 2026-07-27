<template>
  <a-card size="small" title="客户简档" class="customer-profile-panel">
    <a-empty v-if="!customer" description="请选择客户" :image="false" />
    <a-descriptions v-else bordered size="small" :column="1">
      <a-descriptions-item label="姓名">{{ customer.name }}</a-descriptions-item>
      <a-descriptions-item label="客户等级">{{ customer.level }}</a-descriptions-item>
      <a-descriptions-item label="城市">{{ customer.city }}</a-descriptions-item>
      <a-descriptions-item label="职业">{{ customer.occupation }}</a-descriptions-item>
      <a-descriptions-item label="风险偏好">{{ customer.riskPreference }}</a-descriptions-item>
      <a-descriptions-item label="投资期限">{{ customer.investmentHorizon }}</a-descriptions-item>
      <a-descriptions-item label="资产规模">{{ customer.aumBand }}</a-descriptions-item>
      <a-descriptions-item label="投资目标">
        <div class="tag-list">
          <a-tag v-for="goal in customer.goals" :key="goal" color="gold">{{ goal }}</a-tag>
        </div>
      </a-descriptions-item>
      <a-descriptions-item label="客户标签">
        <div class="tag-list">
          <a-tag v-for="tag in customer.tags" :key="tag" color="blue">{{ tag }}</a-tag>
        </div>
      </a-descriptions-item>
      <a-descriptions-item label="备注">{{ customer.notes }}</a-descriptions-item>
      <a-descriptions-item label="最近联系">{{ customer.lastContactAt }}</a-descriptions-item>
    </a-descriptions>
  </a-card>
</template>

<script setup lang="ts">
import type { RmCustomer } from '@/types/rm'

defineProps<{
  customer: RmCustomer | null
}>()
</script>

<style scoped lang="scss">
.customer-profile-panel {
  height: 100%;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
