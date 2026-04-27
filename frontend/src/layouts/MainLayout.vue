<template>
  <div class="main-layout">
    <div class="layout-header">
      <div class="header-left">
        <div class="header-titles" @click="router.push('/home')">
          <h1 class="system-title">金融产品解析智能体</h1>
          <p class="system-subtitle">FINANCIAL PRODUCT ANALYSIS INTELLIGENT AGENT.</p>
        </div>
      </div>
    </div>
    <div class="layout-content">
      <div class="layout-sidebar">
        <div class="sidebar-top">
          <a-button 
            type="primary" 
            :class="['new-conversation-btn', { 'active': isActiveMenu.chat }]"
            :disabled="showSessionHistory && chatBusy"
            @click="handleNewConversation"
          >
            <PlusOutlined />
            开启新对话
          </a-button>
          <div class="nav-links">
            <a 
              :class="['nav-link', { 'active': isActiveMenu.compare }]"
              @click="handleNav('/fpai/compare')"
            >
              <SwapOutlined />
              <span>产品对比</span>
            </a>
            <a 
              :class="['nav-link', { 'active': isActiveMenu.recommend }]"
              @click="handleNav('/fpai/recommend')"
            >
              <StarOutlined />
              <span>产品推荐</span>
            </a>
          <!--   <a 
              :class="['nav-link', { 'active': isActiveMenu.evidence }]"
              @click="handleNav('/fpai/evidence')"
            >
              <AuditOutlined />
              <span>证据查询</span>
            </a>
            <a 
              :class="['nav-link', { 'active': isActiveMenu.feedback }]"
              @click="handleNav('/fpai/feedback')"
            >
              <MessageOutlined />
              <span>回答反馈</span>
            </a>
            -->
            <a 
              :class="['nav-link', { 'active': isActiveMenu.products }]"
              @click="handleNav('/fpai/products')"
            >
              <UnorderedListOutlined />
              <span>产品列表</span>
            </a>
          </div>
        </div>
        <div class="conversation-history">
          <SessionHistoryList v-if="showSessionHistory" />
        </div>
        <div class="sidebar-bottom">
          <!-- <a class="nav-link">
            <StarOutlined />
            <span>创作助手</span>
          </a>
          <a class="nav-link">
            <AppstoreOutlined />
            <span>资源中心</span>
          </a> -->
          <a-dropdown :trigger="['click']" placement="topLeft">
            <div class="user-info" @click.prevent>
              <a-avatar :size="32" class="user-avatar">
                <UserOutlined />
              </a-avatar>
              <span>{{ userStore.userInfo?.name || 'unknown' }}</span>
            </div>
            <template #overlay>
              <a-menu @click="handleMenuClick">
                <a-menu-item key="profile" style="margin-top: 10px;">
                  <UserOutlined />
                  <span style="margin-left: 10px;">个人信息</span>
                </a-menu-item>
                <a-menu-item v-if="canAccessAdmin" key="settings">
                  <SettingOutlined />
                  <span style="margin-left: 10px;">后台管理</span>
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" style="margin-top: 10px;">
                  <LogoutOutlined />
                  <span style="margin-left: 10px;">退出</span>
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </div>
      <div class="layout-main">
        <router-view />
      </div>
    </div>
    
    <!-- 个人信息弹窗 -->
    <a-modal
      v-model:open="profileModalVisible"
      title="个人信息"
      @ok="handleProfileModalOk"
      @cancel="handleProfileModalCancel"
      :width="600"
      ok-text="保存"
      cancel-text="取消"
    >
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="info" tab="基本信息">
          <a-form
            ref="profileFormRef"
            :model="profileFormData"
            :rules="profileFormRules"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 18 }"
          >
            <a-form-item label="用户名" name="account">
              <a-input v-model:value="profileFormData.account" placeholder="请输入用户名" />
            </a-form-item>
            <a-form-item label="邮箱" name="email">
              <a-input v-model:value="profileFormData.email" placeholder="请输入邮箱" />
            </a-form-item>
            <a-form-item label="工号" name="employee_no">
              <a-input v-model:value="profileFormData.employee_no" placeholder="请输入工号" />
            </a-form-item>
            <a-form-item label="真实姓名" name="name">
              <a-input v-model:value="profileFormData.name" placeholder="请输入真实姓名" />
            </a-form-item>
          </a-form>
        </a-tab-pane>
        <a-tab-pane key="password" tab="修改密码">
          <a-form
            ref="passwordFormRef"
            :model="passwordFormData"
            :rules="passwordFormRules"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 18 }"
          >
            <a-form-item label="当前密码" name="old_password">
              <a-input-password v-model:value="passwordFormData.old_password" placeholder="请输入当前密码" />
            </a-form-item>
            <a-form-item label="新密码" name="new_password">
              <a-input-password v-model:value="passwordFormData.new_password" placeholder="请输入新密码" />
            </a-form-item>
            <a-form-item label="确认密码" name="confirm_password">
              <a-input-password v-model:value="passwordFormData.confirm_password" placeholder="请再次输入新密码" />
            </a-form-item>
          </a-form>
        </a-tab-pane>
      </a-tabs>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import {
  PlusOutlined,
  SwapOutlined,
  StarOutlined,
  UnorderedListOutlined,
  UserOutlined,
  SettingOutlined,
  LogoutOutlined,
} from '@ant-design/icons-vue'
import { useUserStore } from '@/store/user'
import { updateCurrentUser, changePassword, getUserInfo, getUserMenus } from '@/api/user'
import { encryptPassword } from '@/utils/crypto'
import SessionHistoryList from '@/components/chat/SessionHistoryList.vue'
import { storage } from '@/utils/storage'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const isAdminByRole = computed(() => {
  const roles = (userStore.userInfo as any)?.roles
  if (!Array.isArray(roles)) return false
  return roles.map((x: any) => String(x).toLowerCase()).includes('admin')
})

const canAccessAdmin = ref(false)
const adminHomePath = ref('/admin/theme-settings')
const chatBusy = ref(false)
const SESSION_STORAGE_KEY = 'chat_session_id'

const initAdminAccess = async () => {
  if (isAdminByRole.value) {
    canAccessAdmin.value = true
    adminHomePath.value = '/admin/theme-settings'
    return
  }
  try {
    const res = await getUserMenus()
    const menus = Array.isArray(res.data) ? res.data : []
    const first = menus.find(m => (m.path || '').startsWith('/admin')) || menus[0]
    if (first?.path) {
      canAccessAdmin.value = true
      adminHomePath.value = first.path
    } else {
      canAccessAdmin.value = false
    }
  } catch {
    canAccessAdmin.value = false
  }
}

watch(
  () => isAdminByRole.value,
  (val) => {
    if (val) {
      canAccessAdmin.value = true
      adminHomePath.value = '/admin/theme-settings'
    } else {
      canAccessAdmin.value = false
      initAdminAccess()
    }
  },
  { immediate: true }
)

// 判断当前激活的菜单项
const isActiveMenu = computed(() => {
  const path = route.path
  return {
    chat: path === '/fpai/chat',
    compare: path === '/fpai/compare',
    recommend: path === '/fpai/recommend',
    report: path === '/fpai/report',
    evidence: path === '/fpai/evidence',
    feedback: path === '/fpai/feedback',
    products: path === '/fpai/products'
  }
})

const showSessionHistory = computed(() => route.path.startsWith('/fpai/chat'))

// 侧栏导航跳转
const handleNav = (path: string) => {
  router.push(path)
}

const handleNewConversation = () => {
  if (showSessionHistory.value && chatBusy.value) return
  storage.remove(SESSION_STORAGE_KEY)
  router.push({ path: '/fpai/chat', query: {} })
}

function onChatLoadingChange(ev: Event) {
  const e = ev as CustomEvent<{ loading?: boolean }>
  chatBusy.value = Boolean(e?.detail?.loading)
}

onMounted(() => {
  window.addEventListener('chat-loading-change', onChatLoadingChange as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('chat-loading-change', onChatLoadingChange as EventListener)
})

// 个人信息弹窗相关状态
const profileModalVisible = ref(false)
const activeTab = ref('info')
const profileFormRef = ref()
const passwordFormRef = ref()

const profileFormData = reactive({
  account: '',
  email: '',
  employee_no: '',
  name: ''
})

const passwordFormData = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

// 验证用户名
const validateUsername = (_rule: any, value: string) => {
  if (!value) {
    return Promise.reject('请输入用户名')
  }
  if (value.length < 3 || value.length > 50) {
    return Promise.reject('用户名长度必须在3-50个字符之间')
  }
  if (!/^[a-zA-Z0-9_]+$/.test(value)) {
    return Promise.reject('用户名只能包含字母、数字和下划线')
  }
  return Promise.resolve()
}

// 验证邮箱
const validateEmail = (_rule: any, value: string) => {
  if (!value) {
    return Promise.reject('请输入邮箱')
  }
  if (value.length > 100) {
    return Promise.reject('邮箱长度不能超过100个字符')
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(value)) {
    return Promise.reject('请输入有效的邮箱地址')
  }
  return Promise.resolve()
}

// 验证手机号
const validatePhone = (_rule: any, value: string) => {
  if (value && value.length > 0) {
    const phoneRegex = /^1[3-9]\d{9}$/
    if (!phoneRegex.test(value)) {
      return Promise.reject('请输入有效的手机号（11位数字，以1开头）')
    }
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
  if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(value)) {
    return Promise.reject('密码必须包含至少一个字母和一个数字')
  }
  return Promise.resolve()
}

// 验证确认密码
const validateConfirmPassword = (_rule: any, value: string) => {
  if (!value) {
    return Promise.reject('请再次输入密码')
  }
  if (value !== passwordFormData.new_password) {
    return Promise.reject('两次输入的密码不一致')
  }
  return Promise.resolve()
}

const profileFormRules = {
  username: [{ validator: validateUsername, required: true, trigger: 'blur' }],
  email: [{ validator: validateEmail, required: true, trigger: 'blur' }],
  phone: [{ validator: validatePhone, required: true, trigger: 'blur' }],
  real_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { max: 50, message: '真实姓名长度不能超过50个字符', trigger: 'blur' }
  ]
}

const passwordFormRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [{ validator: validatePassword, required: true, trigger: 'blur' }],
  confirm_password: [{ validator: validateConfirmPassword, required: true, trigger: 'blur' }]
}

// 监听弹窗打开，加载用户信息
watch(profileModalVisible, async (visible) => {
  if (visible) {
    await loadUserInfo()
  } else {
    // 关闭时重置表单
    activeTab.value = 'info'
    passwordFormData.old_password = ''
    passwordFormData.new_password = ''
    passwordFormData.confirm_password = ''
  }
})

// 加载用户信息
const loadUserInfo = async () => {
  try {
    const res = await getUserInfo()
    const userInfo = res.data
    profileFormData.account = userInfo.account || ''
    profileFormData.email = userInfo.email || ''
    profileFormData.employee_no = userInfo.employee_no || ''
    profileFormData.name = userInfo.name || ''
  } catch (error) {
    console.error('Load user info error:', error)
  }
}

// 保存基本信息
const handleProfileModalOk = async () => {
  try {
    if (activeTab.value === 'info') {
      await profileFormRef.value?.validate()
      await updateCurrentUser({
        id: userStore.userInfo?.id || '',
        account: profileFormData.account,
        email: profileFormData.email,
        employee_no: profileFormData.employee_no,
        name: profileFormData.name
      })
      message.success('个人信息更新成功')
      // 更新 store 中的用户信息
      await userStore.fetchUserInfo()
      profileModalVisible.value = false
    } else if (activeTab.value === 'password') {
      await passwordFormRef.value?.validate()
       // 加密密码
      const encryptedOldPassword = await encryptPassword(passwordFormData.old_password)
      // 加密密码
      const encryptedNewPassword = await encryptPassword(passwordFormData.new_password)
      await changePassword({
        old_password: encryptedOldPassword,
        new_password: encryptedNewPassword
      })
      message.success('密码修改成功')
      // 重置密码表单
      passwordFormData.old_password = ''
      passwordFormData.new_password = ''
      passwordFormData.confirm_password = ''
      activeTab.value = 'info'
    }
  } catch (error: any) {
    if (error?.errorFields) {
      // 表单验证错误
      return
    }
    console.error('Save profile error:', error)
  }
}

// 取消
const handleProfileModalCancel = () => {
  profileModalVisible.value = false
}


const handleMenuClick = ({ key }: { key: string }) => {
  switch (key) {
    case 'profile':
      profileModalVisible.value = true
      break
    case 'settings':
      router.push(adminHomePath.value || '/admin/theme-settings')
      break
    case 'logout':
      Modal.confirm({
        title: '确认退出',
        content: '确定要退出登录吗？',
        onOk: async () => {
          await userStore.logout()
          router.push('/login')
        }
      })
      break
  }
}
</script>

<style scoped lang="scss">
@use 'sass:color';

.main-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(135deg, #f0f5ff 0%, #e6f7ff 50%, #f5f5f5 100%);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: 
      radial-gradient(circle at 20% 30%, rgba($accent-color, 0.08) 0%, transparent 50%),
      radial-gradient(circle at 80% 70%, rgba($primary-color, 0.06) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }
}

// Header 与附件图片一致：深色海军蓝背景、左侧 logo+标题+副标题、右侧控制台链接+用户胶囊
$header-bg: #1e3551;
$header-bg-subtle: #243d5c;
$header-logo-bg: #2a4568;
$header-accent: #36b0f5;
$header-text: #ffffff;
$header-text-muted: #a0b0c0;

.layout-header {
  @include flex-between;
  height: 64px;
  padding: 0 28px;
  background: $header-bg;
  background-image: linear-gradient(180deg, rgba(29, 42, 66, 0.4) 0%, transparent 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  position: relative;
  z-index: 10;

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;

    .header-logo {
      width: 44px;
      height: 44px;
      border-radius: 10px;
      background: $header-logo-bg;
      box-shadow: inset 0 0 20px rgba($header-accent, 0.15);
      @include flex-center;
      .logo-icon {
        font-size: 22px;
        color: $header-accent;
      }
    }

    .header-titles {
      display: flex;
      flex-direction: column;
      gap: 2px;
      cursor: pointer;
      transition: opacity 0.2s;
      &:hover {
        opacity: 0.9;
      }

      .system-title {
        font-size: 18px;
        font-weight: 700;
        color: $header-text;
        margin: 0;
        line-height: 1.3;
        letter-spacing: 0.02em;
      }

      .system-subtitle {
        font-size: 11px;
        color: $header-text-muted;
        margin: 0;
        line-height: 1.4;
        letter-spacing: 0.01em;
      }
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;

    .header-console-link {
      @include flex-center;
      gap: 6px;
      color: $header-text-muted;
      cursor: pointer;
      font-size: 14px;
      transition: color 0.2s;

      &:hover {
        color: $header-text;
      }
    }

    .header-separator {
      color: $header-text-muted;
      font-size: 14px;
      user-select: none;
    }

    .header-user-pill {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      background: $header-logo-bg;
      border-radius: 999px;
      color: $header-text;
      font-size: 14px;
      cursor: pointer;
      transition: background 0.2s;

      &:hover {
        background: color.adjust($header-logo-bg, $lightness: 6%);
      }

      .chevron {
        font-size: 12px;
        opacity: 0.85;
      }
    }
  }
}

.layout-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.layout-sidebar {
  width: $sidebar-width;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(250, 252, 255, 0.95) 100%);
  backdrop-filter: blur(10px);
  border-right: 1px solid rgba($primary-color, 0.1);
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  z-index: 5;

  .sidebar-top {
    padding: 16px;
    border-bottom: 1px solid rgba($primary-color, 0.1);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.5) 0%, transparent 100%);
    position: relative;

    &::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 16px;
      right: 16px;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba($accent-color, 0.3), transparent);
    }

    .new-conversation-btn {
      width: 100%;
      margin-bottom: 16px;
      height: 40px;
      font-size: 14px;
      background: linear-gradient(135deg, $primary-color 0%, $accent-color-light 100%);
      border: none;
      box-shadow: 0 4px 12px rgba($primary-color, 0.3);
      font-weight: 500;
      transition: all 0.3s;

      &:hover {
        background: linear-gradient(135deg, $primary-color-hover 0%, $accent-color 100%);
        box-shadow: 0 6px 16px rgba($primary-color, 0.4);
        transform: translateY(-1px);
      }

      &.active {
        background: linear-gradient(135deg, $primary-color-hover 0%, $accent-color 100%);
        box-shadow: 0 6px 16px rgba($primary-color, 0.5);
        border: 2px solid rgba($primary-color, 0.3);
        transform: translateY(-1px);
      }
    }

    .nav-links {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 16px;

      .nav-link {
        @include flex-center;
        justify-content: flex-start;
        gap: 8px;
        padding: 10px 12px;
        font-size: 15px;
        color: $text-secondary;
        border-radius: 6px;
        transition: all 0.3s;
        position: relative;

        &:hover {
          background: linear-gradient(90deg, rgba($primary-color, 0.08) 0%, rgba($accent-color, 0.04) 100%);
          color: $primary-color;
          transform: translateX(4px);
        }

        &.active {
          background: linear-gradient(90deg, rgba($primary-color, 0.15) 0%, rgba($accent-color, 0.08) 100%);
          color: $primary-color;
          font-weight: 500;
          border-left: 3px solid $primary-color;
          padding-left: 9px; // 调整左边距以保持对齐

          &::before {
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 3px;
            height: 60%;
            //background: $primary-color;
            //border-radius: 0 2px 2px 0;
          }
        }
      }
    }

    .search-input {
      width: 100%;
    }
  }

  .conversation-history {
    flex: 1;
    overflow-y: auto;
    padding: 16px;

    .history-year {
      font-size: 12px;
      color: $text-tertiary;
      margin-bottom: 8px;
    }
  }

  .sidebar-bottom {
    padding: 16px;
    border-top: 1px solid rgba($primary-color, 0.1);
    background: linear-gradient(180deg, transparent 0%, rgba(255, 255, 255, 0.3) 100%);
    position: relative;

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 16px;
      right: 16px;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba($accent-color, 0.3), transparent);
    }

    .nav-link {
      @include flex-center;
      justify-content: flex-start;
      gap: 8px;
      padding: 10px 12px;
      color: $text-secondary;
      border-radius: 6px;
      margin-bottom: 8px;
      transition: all 0.3s;
      position: relative;

      &:hover {
        background: linear-gradient(90deg, rgba($primary-color, 0.08) 0%, rgba($accent-color, 0.04) 100%);
        color: $primary-color;
        transform: translateX(4px);
      }

      &.active {
        background: linear-gradient(90deg, rgba($primary-color, 0.15) 0%, rgba($accent-color, 0.08) 100%);
        color: $primary-color;
        font-weight: 500;
        border-left: 3px solid $primary-color;
        padding-left: 9px; // 调整左边距以保持对齐

        &::before {
          content: '';
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 3px;
          height: 60%;
          background: $primary-color;
          border-radius: 0 2px 2px 0;
        }
      }
    }

    .user-info {
      @include flex-center;
      justify-content: flex-start;
      gap: 8px;
      padding: 8px 12px;
      color: $text-secondary;
      cursor: pointer;
      border-radius: 4px;
      transition: all 0.3s;

      .user-avatar :deep(.anticon) {
        color: $primary-color;
      }

      &:hover {
        background-color: $light-bg-gray;
        color: $primary-color;

        .user-avatar :deep(.anticon) {
          color: $primary-color;
        }
      }
    }
  }
}

.layout-main {
  flex: 1;
  overflow-y: auto;
  background: transparent;
  position: relative;
  z-index: 1;
}

.layout-footer {
  background-color: $light-bg;
  border-top: 1px solid $border-color;
  padding: 16px 24px;

  .input-bar {
    max-width: 1200px;
    margin: 0 auto;

    .input-left {
      @include flex-center;
      gap: 16px;
      margin-bottom: 8px;

      .action-btn {
        color: $primary-color;
        padding: 0;
      }
    }

    .main-input {
      width: 100%;
    }

    .send-icon {
      color: $primary-color;
      cursor: pointer;
    }

    .input-disclaimer {
      font-size: 12px;
      color: $text-tertiary;
      text-align: center;
      margin-top: 8px;
    }
  }
}
</style>
