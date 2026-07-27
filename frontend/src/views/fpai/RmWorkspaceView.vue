<template>
  <div class="rm-workspace-view">
    <div class="workspace-column workspace-column-left">
      <CustomerSelector
        :customers="customers"
        :selected-customer-id="selectedCustomerId"
        @select="handleSelectCustomer"
      />
    </div>
    <div class="workspace-column workspace-column-center">
      <CustomerProfilePanel :customer="selectedCustomer" />
    </div>
    <div class="workspace-column workspace-column-right">
      <TodoPanel
        :customer="selectedCustomer"
        :todos="todos"
        @add-todo="handleAddTodo"
        @toggle-todo="handleToggleTodo"
        @delete-todo="handleDeleteTodo"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CustomerProfilePanel from '@/components/rm/CustomerProfilePanel.vue'
import CustomerSelector from '@/components/rm/CustomerSelector.vue'
import TodoPanel from '@/components/rm/TodoPanel.vue'
import { rmCustomers } from '@/mocks/rmCustomers'
import type { RmCustomer, RmTodo, RmTodoPriority } from '@/types/rm'
import {
  addRmTodo,
  deleteRmTodo,
  getRmTodosByCustomerId,
  toggleRmTodoStatus,
} from '@/utils/rmTodoStorage'

const customers = ref<RmCustomer[]>(rmCustomers)
const selectedCustomerId = ref<string>(customers.value[0]?.id || '')
const todos = ref<RmTodo[]>([])

const selectedCustomer = computed<RmCustomer | null>(() => {
  return customers.value.find((customer) => customer.id === selectedCustomerId.value) || null
})

function syncTodos(customerId: string) {
  todos.value = customerId ? getRmTodosByCustomerId(customerId) : []
}

function handleSelectCustomer(customerId: string) {
  selectedCustomerId.value = customerId
}

function handleAddTodo(input: {
  customerId: string
  title: string
  priority?: RmTodoPriority
  dueDate?: string
}) {
  addRmTodo(input)
  syncTodos(input.customerId)
}

function handleToggleTodo(todoId: string) {
  toggleRmTodoStatus(todoId)
  syncTodos(selectedCustomerId.value)
}

function handleDeleteTodo(todoId: string) {
  deleteRmTodo(todoId)
  syncTodos(selectedCustomerId.value)
}

watch(
  () => selectedCustomerId.value,
  (customerId) => {
    syncTodos(customerId)
  },
  { immediate: true }
)
</script>

<style scoped lang="scss">
.rm-workspace-view {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  gap: 24px;
  height: calc(100vh - 128px);
  margin: 32px;
}

.workspace-column {
  min-width: 0;
  height: 100%;
}
</style>
