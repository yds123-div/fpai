<template>
  <div class="role-management">
    <div class="page-header">
      <div>
        <h2 class="page-title">角色管理</h2>
        <p class="page-desc">维护角色，并为角色分配菜单权限。</p>
      </div>
      <div class="header-actions">
        <a-button @click="load" :loading="loading">刷新</a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon>+</template>
          新建角色
        </a-button>
      </div>
    </div>

    <a-table
      style="margin-top: 12px"
      :data-source="roles"
      :columns="columns"
      :loading="loading"
      row-key="code"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enabled'">
          <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '禁用' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="openEdit(record)">编辑</a-button>
            <a-button size="small" @click="openMenus(record)">菜单权限</a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="roleModalOpen"
      :title="roleMode === 'create' ? '新建角色' : '编辑角色'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="saveRole"
      @cancel="closeRole"
    >
      <a-form layout="vertical">
        <a-form-item label="角色 Code" required>
          <a-input v-model:value="roleForm.code" :disabled="roleMode !== 'create'" placeholder="例如：auditor" />
        </a-form-item>
        <a-form-item label="名称" required>
          <a-input v-model:value="roleForm.name" placeholder="例如：审计员" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="roleForm.description" />
        </a-form-item>
        <a-form-item label="启用">
          <a-switch v-model:checked="roleForm.enabled" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="menusModalOpen"
      title="分配菜单权限"
      width="720px"
      :confirm-loading="savingMenus"
      ok-text="保存"
      cancel-text="取消"
      @ok="saveMenus"
      @cancel="closeMenus"
    >
      <a-alert
        type="info"
        show-icon
        message="提示"
        description="勾选后保存，将覆盖该角色已有的菜单权限。"
        style="margin-bottom: 12px"
      />
      <a-checkbox-group v-model:value="selectedMenuCodes" style="width: 100%">
        <a-row :gutter="[8, 8]">
          <a-col :span="12" v-for="m in menuOptions" :key="m.value">
            <a-checkbox :value="m.value">{{ m.label }}</a-checkbox>
          </a-col>
        </a-row>
      </a-checkbox-group>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { ColumnsType } from 'ant-design-vue/es/table'
import { listMenus, listRoles, upsertRole, getRoleMenus, setRoleMenus, type RoleItem, type MenuItemRbac } from '@/api/rbac'

const loading = ref(false)
const saving = ref(false)
const roles = ref<RoleItem[]>([])
const menus = ref<MenuItemRbac[]>([])

const columns: ColumnsType = [
  { title: 'Code', dataIndex: 'code', key: 'code', width: 140 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
  { title: '描述', dataIndex: 'description', key: 'description' },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
  { title: '操作', key: 'actions', width: 180 }
]

const roleModalOpen = ref(false)
const roleMode = ref<'create' | 'edit'>('create')
const roleForm = ref({ code: '', name: '', description: '', enabled: true })

const menusModalOpen = ref(false)
const savingMenus = ref(false)
const currentRoleCode = ref('')
const selectedMenuCodes = ref<string[]>([])

const menuOptions = computed(() => {
  return (menus.value || []).map(m => ({ label: `${m.name}（${m.code}）`, value: m.code }))
})

async function load() {
  loading.value = true
  try {
    const [r, m] = await Promise.all([listRoles(), listMenus()])
    roles.value = Array.isArray(r.data?.items) ? r.data.items : []
    menus.value = Array.isArray(m.data?.items) ? m.data.items : []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  roleMode.value = 'create'
  roleForm.value = { code: '', name: '', description: '', enabled: true }
  roleModalOpen.value = true
}

function openEdit(r: RoleItem) {
  roleMode.value = 'edit'
  roleForm.value = { code: r.code, name: r.name || '', description: r.description || '', enabled: !!r.enabled }
  roleModalOpen.value = true
}

function closeRole() {
  roleModalOpen.value = false
}

async function saveRole() {
  const p = roleForm.value
  if (!p.code?.trim()) return message.error('角色 code 不能为空')
  if (!p.name?.trim()) return message.error('角色名称不能为空')
  saving.value = true
  try {
    await upsertRole({ ...p })
    message.success('保存成功')
    roleModalOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function openMenus(r: RoleItem) {
  currentRoleCode.value = r.code
  menusModalOpen.value = true
  selectedMenuCodes.value = []
  try {
    const res = await getRoleMenus(r.code)
    selectedMenuCodes.value = Array.isArray(res.data?.items) ? res.data.items : []
  } catch {
    selectedMenuCodes.value = []
  }
}

function closeMenus() {
  menusModalOpen.value = false
  currentRoleCode.value = ''
}

async function saveMenus() {
  if (!currentRoleCode.value) return
  savingMenus.value = true
  try {
    await setRoleMenus(currentRoleCode.value, selectedMenuCodes.value)
    message.success('保存成功')
    menusModalOpen.value = false
  } finally {
    savingMenus.value = false
  }
}

onMounted(() => load())
</script>

<style scoped lang="scss">
.role-management {
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

