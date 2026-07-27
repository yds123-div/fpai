<template>
  <div class="model-management">
    <div class="page-header">
      <div>
        <h2 class="page-title">模型配置</h2>
        <p class="page-desc">管理不同类型的 AI 模型，支持 Ollama 本地模型和远程 API。</p>
      </div>
      <a-button type="primary" @click="openAdd">
        <template #icon>+</template>
        添加模型
      </a-button>
    </div>

    <a-alert
      type="success"
      show-icon
      message="内置模型"
      description="内置模型对所有租户可见，敏感信息会被隐藏，且不可编辑或删除。"
      style="margin-top: 12px"
    />

    <div class="model-list">
      <a-card v-for="m in models" :key="m.id" class="model-card" size="small">
        <div class="card-head">
          <div class="model-name">{{ m.name }}</div>
          <a-tag>{{ m.source === 'ollama' ? 'Ollama' : 'Remote' }}</a-tag>
        </div>
        <div class="card-meta">
          <div class="meta-row"><span class="k">模型名</span><span class="v">{{ m.model_name || '-' }}</span></div>
          <div class="meta-row"><span class="k">Base URL</span><span class="v">{{ m.base_url || '-' }}</span></div>
        </div>
        <div class="card-actions">
          <a-button size="small" @click="openEdit(m)">编辑</a-button>
          <a-button size="small" danger @click="remove(m)">删除</a-button>
        </div>
      </a-card>
      <a-empty v-if="!models.length" description="暂无模型配置" />
    </div>

    <a-modal
      v-model:open="modalOpen"
      title="添加模型"
      width="720px"
      :confirm-loading="saving"
      @ok="save"
      @cancel="close"
    >
      <a-form layout="vertical">
        <a-form-item label="模型来源" required>
          <a-radio-group v-model:value="form.source">
            <a-radio value="ollama">Ollama（本地）</a-radio>
            <a-radio value="remote">Remote API（远程）</a-radio>
          </a-radio-group>
        </a-form-item>

        <a-form-item v-if="form.source === 'remote'" label="服务商">
          <a-select v-model:value="form.vendor" :options="vendorOptions" />
        </a-form-item>

        <a-form-item label="模型名" required>
          <a-input v-model:value="form.model_name" placeholder="用于实际调用，例如：qwen-max、qwen3-32b、gpt-4o" />
        </a-form-item>

        <a-form-item label="Base URL" required>
          <a-input v-model:value="form.base_url" placeholder="例如：http://localhost:11434 或 https://xxx/v1" />
        </a-form-item>

        <a-form-item v-if="form.source === 'remote'" label="API Key（可选）">
          <a-input-password v-model:value="form.api_key" placeholder="不回显已保存的 key" />
        </a-form-item>

        <div class="test-row">
          <a-button :loading="testing" @click="testConn">连接测试</a-button>
          <span v-if="testResult" class="test-result">{{ testResult }}</span>
        </div>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import type { AiModelItem, ModelUpsertBody } from '@/api/models'
import { deleteModel, listModels, testModelConnection, upsertModel } from '@/api/models'

const models = ref<AiModelItem[]>([])
const modalOpen = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref('')

const vendorOptions = [
  { label: '自定义（OpenAI兼容接口）', value: 'custom' },
  { label: 'OpenAI', value: 'openai' },
]

const form = ref<ModelUpsertBody>({
  source: 'ollama',
  vendor: 'custom',
  model_name: '',
  base_url: '',
  api_key: '',
  enabled: true,
})

async function load() {
  const res = await listModels(false)
  models.value = Array.isArray(res.data?.items) ? res.data.items : []
}

function openAdd() {
  testResult.value = ''
  form.value = { source: 'ollama', vendor: 'custom', model_name: '', base_url: '', api_key: '', enabled: true }
  modalOpen.value = true
}

function openEdit(m: AiModelItem) {
  testResult.value = ''
  form.value = {
    id: m.id,
    source: m.source,
    vendor: m.vendor || 'custom',
    model_name: m.model_name || '',
    base_url: m.base_url || '',
    api_key: '',
    enabled: !!m.enabled,
  }
  modalOpen.value = true
}

function close() {
  modalOpen.value = false
  saving.value = false
  testing.value = false
  testResult.value = ''
}

async function testConn() {
  testing.value = true
  testResult.value = ''
  try {
    const res = await testModelConnection({
      source: form.value.source,
      vendor: form.value.vendor,
      model_name: form.value.model_name,
      base_url: form.value.base_url,
      api_key: form.value.api_key || undefined,
    })
    const sample = Array.isArray(res.data?.sample) ? res.data.sample : []
    testResult.value = sample.length ? `连接成功（示例：${sample.slice(0, 3).join(', ')}）` : '连接成功'
  } catch (e: any) {
    testResult.value = e?.message || '连接失败'
  } finally {
    testing.value = false
  }
}

async function save() {
  if (!form.value.model_name?.trim()) return antMessage.error('请输入模型名')
  if (!form.value.base_url?.trim()) return antMessage.error('请输入 Base URL')
  saving.value = true
  try {
    await upsertModel(form.value)
    antMessage.success('保存成功')
    modalOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(m: AiModelItem) {
  await deleteModel(m.id)
  antMessage.success('已删除')
  await load()
}

onMounted(() => {
  load()
})
</script>

<style scoped lang="scss">
.model-management {
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
}
.page-desc {
  color: var(--text-secondary, #666);
  font-size: 14px;
  margin: 0;
}

.model-list {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.model-card {
  border-radius: 10px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.model-name {
  font-weight: 600;
}
.card-meta {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
}
.meta-row {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.meta-row .k {
  width: 64px;
  color: rgba(0, 0, 0, 0.45);
}
.meta-row .v {
  flex: 1;
  word-break: break-all;
}
.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.test-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}
.test-result {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
}
</style>
