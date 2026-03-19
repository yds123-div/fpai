<template>
  <div class="menu-management">
    <div class="page-header">
      <div>
        <h2 class="page-title">菜单管理</h2>
        <p class="page-desc">维护后台菜单项（code/path/icon/sort）。</p>
      </div>
      <div class="header-actions">
        <a-button @click="load" :loading="loading">刷新</a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon>+</template>
          新建菜单
        </a-button>
      </div>
    </div>

    <a-table
      style="margin-top: 12px"
      :data-source="menus"
      :columns="columns"
      :loading="loading"
      row-key="code"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '禁用' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="openEdit(record)">编辑</a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="modalOpen"
      :title="mode === 'create' ? '新建菜单' : '编辑菜单'"
      width="720px"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="save"
      @cancel="close"
    >
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="菜单 Code" required>
              <a-input v-model:value="form.code" :disabled="mode !== 'create'" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="名称" required>
              <a-input v-model:value="form.name" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="16">
            <a-form-item label="路径（path）">
              <a-input v-model:value="form.path" placeholder="/admin/xxx" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="图标（icon）">
              <a-input v-model:value="form.icon" placeholder="user/setting/..." />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item label="排序">
              <a-input-number v-model:value="form.sort_order" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="父菜单ID（可选）">
              <a-input-number v-model:value="form.parent_id" :min="1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="启用">
              <a-switch v-model:checked="form.enabled" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { ColumnsType } from 'ant-design-vue/es/table'
import { listMenus, upsertMenu, type MenuItemRbac } from '@/api/rbac'

const loading = ref(false)
const saving = ref(false)
const menus = ref<MenuItemRbac[]>([])

const columns: ColumnsType = [
  { title: 'Code', dataIndex: 'code', key: 'code', width: 160 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
  { title: 'Path', dataIndex: 'path', key: 'path' },
  { title: 'Icon', dataIndex: 'icon', key: 'icon', width: 120 },
  { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 80 },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
  { title: '操作', key: 'actions', width: 120 }
]

const modalOpen = ref(false)
const mode = ref<'create' | 'edit'>('create')
const form = ref({
  code: '',
  name: '',
  path: '',
  icon: '',
  sort_order: 0,
  parent_id: null as number | null,
  enabled: true
})

async function load() {
  loading.value = true
  try {
    const res = await listMenus()
    menus.value = Array.isArray(res.data?.items) ? res.data.items : []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  mode.value = 'create'
  form.value = { code: '', name: '', path: '', icon: '', sort_order: 0, parent_id: null, enabled: true }
  modalOpen.value = true
}

function openEdit(m: MenuItemRbac) {
  mode.value = 'edit'
  form.value = {
    code: m.code,
    name: m.name || '',
    path: m.path || '',
    icon: m.icon || '',
    sort_order: m.sort_order || 0,
    parent_id: m.parent_id ?? null,
    enabled: !!m.enabled
  }
  modalOpen.value = true
}

function close() {
  modalOpen.value = false
}

async function save() {
  const p = form.value
  if (!p.code?.trim()) return message.error('菜单 code 不能为空')
  if (!p.name?.trim()) return message.error('菜单名称不能为空')
  saving.value = true
  try {
    await upsertMenu({ ...p })
    message.success('保存成功')
    modalOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(() => load())
</script>

<style scoped lang="scss">
.menu-management {
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

