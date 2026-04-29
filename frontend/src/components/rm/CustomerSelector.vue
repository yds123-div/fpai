<template>
  <a-card size="small" title="客户列表" class="customer-selector">
    <a-empty v-if="customers.length === 0" description="暂无客户" :image="false" />
    <div v-else class="customer-list">
      <button
        v-for="customer in customers"
        :key="customer.id"
        type="button"
        :class="['customer-item', { active: customer.id === selectedCustomerId }]"
        @click="handleSelect(customer.id)"
      >
        <div class="customer-item-head">
          <span class="customer-name">{{ customer.name }}</span>
          <a-tag color="blue">{{ customer.level }}</a-tag>
        </div>
        <div class="customer-meta">
          <span>{{ customer.city }}</span>
          <span>{{ customer.aumBand }}</span>
        </div>
        <div v-if="customer.tags.length" class="customer-tags">
          <a-tag v-for="tag in customer.tags" :key="tag">{{ tag }}</a-tag>
        </div>
        <div class="customer-contact">最近联系：{{ customer.lastContactAt }}</div>
      </button>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import type { RmCustomer } from '@/types/rm'

const props = defineProps<{
  customers: RmCustomer[]
  selectedCustomerId?: string
}>()

const emit = defineEmits<{
  (e: 'select', customerId: string): void
}>()

function handleSelect(customerId: string) {
  if (!customerId || customerId === props.selectedCustomerId) return
  emit('select', customerId)
}
</script>

<style scoped lang="scss">
.customer-selector {
  height: 100%;
}

.customer-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.customer-item {
  width: 100%;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.customer-item:hover {
  border-color: rgba(22, 119, 255, 0.35);
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.08);
}

.customer-item.active {
  border-color: #1677ff;
  background: #f0f7ff;
  box-shadow: 0 6px 16px rgba(22, 119, 255, 0.12);
}

.customer-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.customer-name {
  font-size: 15px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.88);
}

.customer-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
  font-size: 13px;
  color: #595959;
}

.customer-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.customer-contact {
  margin-top: 10px;
  font-size: 12px;
  color: #8c8c8c;
}
</style>

