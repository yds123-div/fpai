<template>
  <div class="user-management">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
      <a-button type="primary" @click="handleCreate">
        <PlusOutlined />
        新建用户
      </a-button>
    </div>
    <div class="search-section">
      <a-form :model="searchForm" layout="inline" class="search-form">
        <a-form-item label="账号">
          <a-input
            v-model:value="searchForm.account"
            placeholder="请输入账号"
            allow-clear
          />
        </a-form-item>
        <a-form-item>
          <a-button @click="handleReset">重置</a-button>
          <a-button type="primary" @click="handleSearch" style="margin-left: 8px">
            查询
          </a-button>
        </a-form-item>
      </a-form>
    </div>
    <div class="table-section">
      <div class="section-header">
        <h3 class="section-title">用户列表</h3>
      </div>
      <a-table
        :columns="columns"
        :data-source="tableData"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="handleEdit(record)">编辑</a-button>
              <a-button type="link" size="small" @click="handleResetPassword(record)">重置密码</a-button>
              <a-button type="link" danger size="small" @click="handleDelete(record)">删除</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>
    <a-modal
      v-model:open="modalVisible"
      :title="modalTitle"
      @ok="handleModalOk"
      @cancel="handleModalCancel"
    >
      <a-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 18 }"
      >
        <a-form-item label="账号" name="account">
          <a-input v-model:value="formData.account" :disabled="!isCreate" placeholder="请输入账号" />
        </a-form-item>
        <a-form-item v-if="isCreate" label="密码" name="password">
          <a-input-password v-model:value="formData.password" placeholder="请输入密码" />
        </a-form-item>
        <a-form-item label="姓名" name="name">
          <a-input v-model:value="formData.name" placeholder="请输入姓名" />
        </a-form-item>
        <a-form-item label="工号" name="employee_no">
          <a-input v-model:value="formData.employee_no" placeholder="请输入工号" />
        </a-form-item>
        <a-form-item label="邮箱" name="email">
          <a-input v-model:value="formData.email" placeholder="请输入邮箱" />
        </a-form-item>
      </a-form>
    </a-modal>
    <!-- 重置密码模态框 -->
    <a-modal
      v-model:open="resetPasswordModalVisible"
      title="重置用户密码"
      @ok="handleResetPasswordOk"
      @cancel="handleResetPasswordCancel"
      ok-text="确定"
      cancel-text="取消"
    >
      <a-form
        ref="resetPasswordFormRef"
        :model="resetPasswordFormData"
        :rules="resetPasswordFormRules"
        :label-col="{ span: 6 }"
        :wrapper-col="{ span: 18 }"
      >
        <a-form-item label="账号">
          <a-input :value="currentUser?.account" disabled />
        </a-form-item>
        <a-form-item label="姓名">
          <a-input :value="currentUser?.name" disabled />
        </a-form-item>
        <a-form-item label="新密码" name="new_password">
          <a-input-password v-model:value="resetPasswordFormData.new_password" placeholder="请输入新密码" />
        </a-form-item>
        <a-form-item label="确认密码" name="confirm_password">
          <a-input-password v-model:value="resetPasswordFormData.confirm_password" placeholder="请再次输入新密码" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import {
  getUsersList,
  createUser,
  updateUser,
  deleteUser,
  getUserDetail,
  resetUserPassword,
  type User
} from '@/api/user'

const loading = ref(false)
const modalVisible = ref(false)
const isCreate = ref(true)
const modalTitle = ref('新建用户')
const formRef = ref()

// 重置密码相关状态（currentUser 用于重置密码弹窗）
const currentUser = ref<User | null>(null)
const resetPasswordModalVisible = ref(false)
const resetPasswordFormRef = ref()
const resetPasswordFormData = reactive({
  new_password: '',
  confirm_password: ''
})

const searchForm = reactive({
  account: ''
})

interface FormData {
  id?: string | number
  account: string
  password: string
  name: string
  employee_no: string
  email: string
}

const formData = reactive<FormData>({
  id: undefined,
  account: '',
  password: '',
  name: '',
  employee_no: '',
  email: ''
})

// 验证账号格式
const validateAccount = (_rule: any, value: string) => {
  if (!value) {
    return Promise.reject('请输入账号')
  }
  if (value.length < 3 || value.length > 50) {
    return Promise.reject('账号长度必须在3-50个字符之间')
  }
  if (!/^[a-zA-Z0-9_]+$/.test(value)) {
    return Promise.reject('账号只能包含字母、数字和下划线')
  }
  return Promise.resolve()
}

// 验证邮箱格式（选填时校验格式）
const validateEmail = (_rule: any, value: string) => {
  if (value && value.length > 0) {
    if (value.length > 50) return Promise.reject('邮箱长度不能超过50个字符')
    const emailRegex = /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/
    if (!emailRegex.test(value)) return Promise.reject('请输入有效的邮箱地址')
  }
  return Promise.resolve()
}

// 验证密码强度
const validatePassword = (_rule: any, value: string) => {
  if (!value) {
    return Promise.reject('请输入密码')
  }
  if (value.length < 6 || value.length > 20) {
    return Promise.reject('密码长度必须在6-20个字符之间')
  }
  // 密码强度：至少包含字母和数字
  if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(value)) {
    return Promise.reject('密码必须包含至少一个字母和一个数字')
  }
  return Promise.resolve()
}

const formRules = {
  account: [{ validator: validateAccount, required: true, trigger: 'blur' }],
  password: [{ validator: validatePassword, trigger: 'blur' }],
  name: [
    { required: false },
    { max: 50, message: '姓名长度不能超过50个字符', trigger: 'blur' }
  ],
  employee_no: [{ max: 50, message: '工号长度不能超过50个字符', trigger: 'blur' }],
  email: [{ validator: validateEmail, trigger: 'blur' }]
}

// 验证确认密码
const validateConfirmPassword = (_rule: any, value: string) => {
  if (!value) {
    return Promise.reject('请再次输入密码')
  }
  if (value !== resetPasswordFormData.new_password) {
    return Promise.reject('两次输入的密码不一致')
  }
  return Promise.resolve()
}

// 重置密码表单验证规则
const resetPasswordFormRules = {
  new_password: [{ validator: validatePassword, required: true, trigger: 'blur' }],
  confirm_password: [{ validator: validateConfirmPassword, required: true, trigger: 'blur' }]
}

const tableData = ref<User[]>([])

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`
})

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
  { title: '账号', dataIndex: 'account', key: 'account', width: 120 },
  { title: '姓名', dataIndex: 'name', key: 'name', width: 120 },
  { title: '工号', dataIndex: 'employee_no', key: 'employee_no', width: 120 },
  { title: '邮箱', dataIndex: 'email', key: 'email', width: 180 },
  { title: '操作', key: 'action', width: 220, fixed: 'right' }
]

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getUsersList({
      page: pagination.current,
      page_size: pagination.pageSize,
      account: searchForm.account || undefined
    })
    tableData.value = res.items || []
    pagination.total = res.total ?? 0
  } catch (error: any) {
    message.error(error?.message || '获取用户列表失败')
    tableData.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.current = 1
  fetchData()
}

const handleReset = () => {
  searchForm.account = ''
  pagination.current = 1
  fetchData()
}

const handleTableChange = (pag: any) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchData()
}

const handleCreate = () => {
  isCreate.value = true
  modalTitle.value = '新建用户'
  Object.assign(formData, {
    id: undefined,
    account: '',
    password: '',
    name: '',
    employee_no: '',
    email: ''
  })
  modalVisible.value = true
}

const handleModalOk = async () => {
  try {
    await formRef.value?.validate()
    if (isCreate.value) {
      if (!formData.password) {
        message.error('请输入密码')
        return
      }
      await createUser({
        account: formData.account,
        password: formData.password,
        name: formData.name || undefined,
        employee_no: formData.employee_no || undefined,
        email: formData.email || undefined
      })
      message.success('创建成功')
    } else {
      await updateUser(formData.id!, {
        name: formData.name || undefined,
        employee_no: formData.employee_no || undefined,
        email: formData.email || undefined
      })
      message.success('更新成功')
    }
    modalVisible.value = false
    fetchData()
  } catch (error: any) {
    if (error?.errorFields) return
    message.error(error?.message || '操作失败')
  }
}

const handleModalCancel = () => {
  modalVisible.value = false
}

// 编辑用户
const handleEdit = async (record: User) => {
  try {
    const res = await getUserDetail(record.id)
    const userData = (res.data || record) as User
    isCreate.value = false
    modalTitle.value = '编辑用户'
    Object.assign(formData, {
      id: userData.id,
      account: userData.account,
      password: '',
      name: userData.name ?? '',
      employee_no: userData.employee_no ?? '',
      email: userData.email ?? ''
    })
    modalVisible.value = true
  } catch (error: any) {
    message.error(error?.message || '获取用户详情失败')
  }
}

// 删除用户
const handleDelete = (record: User) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除用户 "${record.account}" 吗？此操作不可恢复！`,
    okText: '删除',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      try {
        await deleteUser(record.id)
        message.success('删除成功')
        fetchData()
      } catch (error: any) {
        console.error('Delete error:', error)
      }
    }
  })
}

// 重置密码
const handleResetPassword = (record: User) => {
  currentUser.value = record
  resetPasswordFormData.new_password = ''
  resetPasswordFormData.confirm_password = ''
  resetPasswordModalVisible.value = true
}

// 确认重置密码
const handleResetPasswordOk = async () => {
  try {
    await resetPasswordFormRef.value?.validate()
    if (!currentUser.value) {
      message.error('用户信息不存在')
      return
    }
    await resetUserPassword(currentUser.value.id, {
      newPassword: resetPasswordFormData.new_password
    })
    message.success('密码重置成功')
    resetPasswordModalVisible.value = false
    resetPasswordFormData.new_password = ''
    resetPasswordFormData.confirm_password = ''
    currentUser.value = null
  } catch (error: any) {
    if (error?.errorFields) {
      // 表单验证错误，不显示错误消息
      return
    }
    console.error('Reset password error:', error)
  }
}

// 取消重置密码
const handleResetPasswordCancel = () => {
  resetPasswordModalVisible.value = false
  resetPasswordFormData.new_password = ''
  resetPasswordFormData.confirm_password = ''
  currentUser.value = null
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped lang="scss">
.user-management {
  padding: 24px;
  background: transparent;
  min-height: 100%;
}

.page-header {
  @include flex-between;
  margin-bottom: 24px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 252, 255, 0.98) 100%);
  backdrop-filter: blur(10px);
  padding: 20px 24px;
  border-radius: 8px;
  border: 1px solid rgba($primary-color, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(180deg, $accent-color, $primary-color);
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
    background: linear-gradient(135deg, $text-primary 0%, $primary-color 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
  }
}

.search-section {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 252, 255, 0.98) 100%);
  backdrop-filter: blur(10px);
  padding: 24px;
  border-radius: 8px;
  border: 1px solid rgba($primary-color, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-bottom: 24px;

  .search-form {
    width: 100%;
  }
}

.table-section {
  flex: 1;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 252, 255, 0.98) 100%);
  backdrop-filter: blur(10px);
  padding: 24px;
  border-radius: 8px;
  border: 1px solid rgba($primary-color, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

  .section-header {
    margin-bottom: 16px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: $text-primary;
    margin: 0;
    position: relative;
    padding-left: 12px;

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 3px;
      height: 16px;
      background: linear-gradient(180deg, $accent-color, $primary-color);
      border-radius: 2px;
    }
  }
}
</style>
