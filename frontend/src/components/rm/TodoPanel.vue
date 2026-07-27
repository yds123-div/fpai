<template>
  <a-card size="small" title="客户待办" class="todo-panel">
    <a-empty v-if="!customer" description="请选择客户" :image="false" />
    <template v-else>
      <a-form layout="vertical" class="todo-form" @finish="handleSubmit">
        <a-form-item label="待办内容">
          <a-textarea
            v-model:value="draftTitle"
            placeholder="输入待办内容"
            :auto-size="{ minRows: 2, maxRows: 4 }"
            allow-clear
          />
        </a-form-item>
        <a-form-item label="优先级">
          <a-select
            v-model:value="draftPriority"
            :options="priorityOptions"
            placeholder="选择优先级"
          />
        </a-form-item>
        <a-form-item label="截止日期">
          <a-input
            v-model:value="draftDueDate"
            placeholder="选填，如 2026-05-01"
            allow-clear
          />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" block @click="handleSubmit">新增待办</a-button>
        </a-form-item>
      </a-form>

      <a-empty v-if="todos.length === 0" description="当前客户暂无待办" :image="false" />
      <div v-else class="todo-list">
        <div v-for="todo in todos" :key="todo.id" :class="['todo-item', { done: todo.status === 'done' }]">
          <div class="todo-item-main">
            <div class="todo-title-row">
              <button type="button" class="todo-toggle" @click="emit('toggleTodo', todo.id)">
                {{ todo.status === 'done' ? '已完成' : '待处理' }}
              </button>
              <span class="todo-title">{{ todo.title }}</span>
            </div>
            <div class="todo-meta">
              <a-tag :color="priorityColorMap[todo.priority]">{{ priorityLabelMap[todo.priority] }}</a-tag>
              <span v-if="todo.dueDate">截止：{{ todo.dueDate }}</span>
              <span>来源：{{ todo.source === 'manual' ? '手动创建' : '跟进生成' }}</span>
            </div>
          </div>
          <button type="button" class="todo-delete" @click="emit('deleteTodo', todo.id)">删除</button>
        </div>
      </div>
    </template>
  </a-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { RmCustomer, RmTodo, RmTodoPriority } from '@/types/rm'

const props = defineProps<{
  customer: RmCustomer | null
  todos: RmTodo[]
}>()

const emit = defineEmits<{
  (e: 'addTodo', input: { customerId: string; title: string; priority?: RmTodoPriority; dueDate?: string }): void
  (e: 'toggleTodo', todoId: string): void
  (e: 'deleteTodo', todoId: string): void
}>()

const priorityOptions: Array<{ label: string; value: RmTodoPriority }> = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
]

const priorityLabelMap: Record<RmTodoPriority, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

const priorityColorMap: Record<RmTodoPriority, string> = {
  high: 'red',
  medium: 'gold',
  low: 'blue',
}

const draftTitle = ref('')
const draftPriority = ref<RmTodoPriority>('medium')
const draftDueDate = ref('')

watch(
  () => props.customer?.id,
  () => {
    draftTitle.value = ''
    draftPriority.value = 'medium'
    draftDueDate.value = ''
  }
)

function handleSubmit() {
  const customerId = props.customer?.id || ''
  const title = draftTitle.value.trim()
  if (!customerId) return
  if (!title) {
    message.warning('请输入待办内容')
    return
  }
  emit('addTodo', {
    customerId,
    title,
    priority: draftPriority.value,
    dueDate: draftDueDate.value.trim() || undefined,
  })
  draftTitle.value = ''
  draftPriority.value = 'medium'
  draftDueDate.value = ''
}
</script>

<style scoped lang="scss">
.todo-panel {
  height: 100%;
}

.todo-form {
  margin-bottom: 16px;
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: #ffffff;
}

.todo-item.done {
  background: #fafafa;
}

.todo-item-main {
  flex: 1;
  min-width: 0;
}

.todo-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.todo-toggle {
  flex-shrink: 0;
  border: none;
  border-radius: 999px;
  background: #e6f4ff;
  color: #1677ff;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.todo-item.done .todo-toggle {
  background: #f6ffed;
  color: #389e0d;
}

.todo-title {
  font-size: 14px;
  line-height: 20px;
  color: rgba(0, 0, 0, 0.88);
  word-break: break-word;
}

.todo-item.done .todo-title {
  color: #8c8c8c;
  text-decoration: line-through;
}

.todo-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  font-size: 12px;
  color: #8c8c8c;
}

.todo-delete {
  flex-shrink: 0;
  border: none;
  border-radius: 6px;
  background: #fff1f0;
  color: #cf1322;
  padding: 6px 10px;
  cursor: pointer;
}
</style>

