<template>
  <div class="skill-management">
    <div class="page-header">
      <div>
        <h2 class="page-title">Skill 管理</h2>
        <p class="page-desc">导入/查看/删除 Skills（导入为注册 Python 模块路径，需包含 run(question, ctx)）。</p>
      </div>
      <div class="header-actions">
        <a-button @click="load" :loading="loading">刷新</a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon>+</template>
          导入 Skill
        </a-button>
      </div>
    </div>

    <a-table
      style="margin-top: 12px"
      :data-source="items"
      :columns="columns"
      :loading="loading"
      row-key="skill_key"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '禁用' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'type'">
          <a-tag :color="record.type === 'builtin' ? 'blue' : 'purple'">{{ record.type }}</a-tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="openEdit(record)">编辑</a-button>
            <a-button size="small" danger :disabled="record.type === 'builtin'" @click="remove(record)">删除</a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="modalOpen"
      :title="mode === 'create' ? '导入 Skill' : '编辑 Skill'"
      width="860px"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="save"
      @cancel="close"
    >
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="Skill Key" required>
              <a-input v-model:value="form.skill_key" :disabled="mode !== 'create'" placeholder="例如：custom_xxx" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="名称" required>
              <a-input v-model:value="form.name" placeholder="展示名" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="16">
            <a-form-item label="module_path" required>
              <a-input v-model:value="form.module_path" placeholder="例如：agents.skills.product_compare.runtime" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="启用">
              <a-switch v-model:checked="form.enabled" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-input v-model:value="form.description" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import type { ColumnsType } from 'ant-design-vue/es/table'
import { createSkill, deleteSkill, listSkills, updateSkill, type SkillProfile, type SkillUpsertBody } from '@/api/skills'

const loading = ref(false)
const saving = ref(false)
const modalOpen = ref(false)
const mode = ref<'create' | 'edit'>('create')

const items = ref<SkillProfile[]>([])

const columns: ColumnsType = [
  { title: 'Key', dataIndex: 'skill_key', key: 'skill_key', width: 180 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 100 },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
  { title: 'module_path', dataIndex: 'module_path', key: 'module_path' },
  { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180 },
  { title: '操作', key: 'actions', width: 160 }
]

const form = ref<SkillUpsertBody>({
  skill_key: '',
  name: '',
  enabled: true,
  module_path: '',
  description: ''
})

async function load() {
  loading.value = true
  try {
    const res = await listSkills(false)
    items.value = Array.isArray(res.data?.items) ? res.data.items : []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  mode.value = 'create'
  form.value = { skill_key: '', name: '', enabled: true, module_path: '', description: '' }
  modalOpen.value = true
}

function openEdit(r: SkillProfile) {
  mode.value = 'edit'
  form.value = {
    skill_key: r.skill_key,
    name: r.name || '',
    enabled: !!r.enabled,
    module_path: r.module_path || '',
    description: r.description || ''
  }
  modalOpen.value = true
}

function close() {
  modalOpen.value = false
}

async function save() {
  const p = { ...form.value }
  if (!p.skill_key?.trim()) return message.error('skill_key 不能为空')
  if (!p.name?.trim()) return message.error('名称不能为空')
  if (!p.module_path?.trim()) return message.error('module_path 不能为空')
  saving.value = true
  try {
    if (mode.value === 'create') {
      await createSkill(p)
      message.success('导入成功')
    } else {
      await updateSkill(p.skill_key, p)
      message.success('保存成功')
    }
    modalOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function remove(r: SkillProfile) {
  Modal.confirm({
    title: '确认删除',
    content: `确定删除 skill：${r.skill_key} 吗？（仅删除自定义 skill）`,
    okText: '删除',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: async () => {
      await deleteSkill(r.skill_key)
      message.success('删除成功')
      await load()
    }
  })
}

onMounted(() => load())
</script>

<style scoped lang="scss">
.skill-management {
  padding: 16px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.page-desc {
  margin: 6px 0 0 0;
  color: rgba(0, 0, 0, 0.6);
}
.header-actions {
  display: flex;
  gap: 8px;
}
</style>

