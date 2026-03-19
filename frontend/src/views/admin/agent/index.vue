<template>
  <div class="agent-management">
    <div class="page-header">
      <div>
        <h2 class="page-title">Agent 管理</h2>
        <p class="page-desc">管理内置/自定义 Agent，支持编辑提示词与模型选择（仅管理员可用）。</p>
      </div>
      <div class="header-actions">
        <a-button @click="load" :loading="loading">刷新</a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon>+</template>
          新建 Agent
        </a-button>
      </div>
    </div>

    <a-alert
      type="info"
      show-icon
      message="说明"
      description="MVP：自定义 agent 仅用于管理，暂不参与对话路由；内置 agent 支持配置覆盖并即时生效。"
      style="margin-top: 12px"
    />

    <a-table
      style="margin-top: 12px"
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :row-key="(r: AgentProfile) => r.agent_key"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '禁用' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'type'">
          <a-tag :color="record.type === 'builtin' ? 'blue' : 'purple'">{{ record.type }}</a-tag>
        </template>
        <template v-else-if="column.key === 'model_id'">
          <span>{{ record.model_id ?? '-' }}</span>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="openEdit(record)">编辑</a-button>
            <a-button
              size="small"
              danger
              :disabled="record.type === 'builtin'"
              @click="remove(record)"
            >
              删除
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="modalOpen"
      :title="editingMode === 'create' ? '新建 Agent' : '编辑 Agent'"
      width="920px"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="save"
      @cancel="close"
    >
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="Agent Key" required>
              <a-input v-model:value="form.agent_key" :disabled="editingMode !== 'create'" placeholder="例如：custom_xxx" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="名称" required>
              <a-input v-model:value="form.name" placeholder="展示名" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="类型">
              <a-select v-model:value="form.type" :disabled="editingMode !== 'create'">
                <a-select-option value="custom">custom</a-select-option>
                <a-select-option value="builtin">builtin</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="启用">
              <a-switch v-model:checked="form.enabled" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="模型">
              <a-select
                v-model:value="form.model_id"
                allow-clear
                placeholder="选择模型（model_id）"
                :options="modelOptions"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="Skills（按顺序尝试）">
          <a-select
            v-model:value="form.skill_keys"
            mode="multiple"
            allow-clear
            placeholder="选择该 Agent 使用的 skills"
            :options="skillOptions"
          />
        </a-form-item>

        <a-form-item label="System Prompt（提示词）">
          <a-textarea v-model:value="form.system_prompt" :auto-size="{ minRows: 10, maxRows: 20 }" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import type { ColumnsType } from 'ant-design-vue/es/table'
import { listAgents, createAgent, updateAgent, deleteAgent, type AgentProfile, type AgentUpsertBody } from '@/api/agents'
import { listModels, type AiModelItem } from '@/api/models'
import { listSkills, type SkillProfile } from '@/api/skills'

const loading = ref(false)
const saving = ref(false)
const modalOpen = ref(false)
const editingMode = ref<'create' | 'edit'>('create')

const items = ref<AgentProfile[]>([])
const models = ref<AiModelItem[]>([])
const skills = ref<SkillProfile[]>([])

const modelOptions = computed(() => {
  return (models.value || []).map(m => ({ label: `${m.id} / ${m.name}`, value: m.id }))
})

const skillOptions = computed(() => {
  return (skills.value || [])
    .filter(s => !!s.enabled && !s.deleted_at)
    .map(s => ({ label: `${s.skill_key} / ${s.name}`, value: s.skill_key }))
})

const columns: ColumnsType = [
  { title: 'Key', dataIndex: 'agent_key', key: 'agent_key', width: 180 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 100 },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
  { title: '模型ID', dataIndex: 'model_id', key: 'model_id', width: 90 },
  { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at' },
  { title: '操作', key: 'actions', width: 160 }
]

const form = ref<AgentUpsertBody>({
  agent_key: '',
  name: '',
  type: 'custom',
  enabled: true,
  system_prompt: '',
  skill_keys: [],
  model_id: null
})

function normalizeSkillKeys(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map(x => String(x)).filter(x => x.trim())
  if (typeof raw === 'string') {
    const s = raw.trim()
    if (!s) return []
    try {
      const obj = JSON.parse(s)
      if (Array.isArray(obj)) return obj.map(x => String(x)).filter(x => x.trim())
    } catch {
      return []
    }
  }
  return []
}

async function load() {
  loading.value = true
  try {
    const [a, m, s] = await Promise.all([listAgents(false), listModels(false), listSkills(false)])
    items.value = Array.isArray(a.data?.items) ? a.data.items : []
    models.value = Array.isArray(m.data?.items) ? m.data.items : []
    skills.value = Array.isArray(s.data?.items) ? s.data.items : []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingMode.value = 'create'
  form.value = { agent_key: '', name: '', type: 'custom', enabled: true, system_prompt: '', skill_keys: [], model_id: null }
  modalOpen.value = true
}

function openEdit(r: AgentProfile) {
  editingMode.value = 'edit'
  form.value = {
    agent_key: r.agent_key,
    name: r.name || '',
    type: (r.type as any) || 'custom',
    enabled: !!r.enabled,
    system_prompt: r.system_prompt || '',
    skill_keys: normalizeSkillKeys((r as any).skill_keys),
    model_id: r.model_id ?? null
  }
  modalOpen.value = true
}

function close() {
  modalOpen.value = false
}

async function save() {
  const payload = { ...form.value }
  if (!payload.agent_key?.trim()) {
    message.error('agent_key 不能为空')
    return
  }
  if (!payload.name?.trim()) {
    message.error('名称不能为空')
    return
  }
  saving.value = true
  try {
    if (editingMode.value === 'create') {
      await createAgent(payload)
      message.success('创建成功')
    } else {
      await updateAgent(payload.agent_key, payload)
      message.success('保存成功')
    }
    modalOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function remove(r: AgentProfile) {
  Modal.confirm({
    title: '确认删除',
    content: `确定删除 agent：${r.agent_key} 吗？（仅删除自定义 agent）`,
    okText: '删除',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: async () => {
      await deleteAgent(r.agent_key)
      message.success('删除成功')
      await load()
    }
  })
}

onMounted(() => {
  load()
})
</script>

<style scoped lang="scss">
.agent-management {
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

