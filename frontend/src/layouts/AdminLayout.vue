<template>
  <div class="admin-layout">
    <div class="admin-sidebar">
      <div class="sidebar-header">
        <h2 class="system-title">金融产品解析智能体</h2>
        <div class="section-title">后台管理</div>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        class="admin-menu"
        @select="handleMenuSelect"
      >
        <template v-for="menu in menuList" :key="`menu-${menu.code}`">
          <MenuItemRecursive :menu="menu" :get-icon="getIcon" />
        </template>
        <!-- 固定菜单项：主题样式设置 -->
        <a-menu-item key="theme-settings">
          <Icons.SettingOutlined />
          <span>主题样式设置</span>
        </a-menu-item>
      </a-menu>
      <div class="sidebar-footer">
        <a-dropdown :trigger="['click']" placement="topLeft">
            <div class="user-info" @click.prevent>
              <a-avatar :size="32" class="user-avatar">
                <Icons.UserOutlined />
              </a-avatar>
              <span>{{ userStore.userInfo?.name || 'unknown' }}</span>
            </div>
            <template #overlay>
              <a-menu @click="handleMenuClick">
                <a-menu-item key="home" style="margin-top: 10px;">
                  <Icons.HomeOutlined />
                  <span style="margin-left: 10px;">返回主页面</span>
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" style="margin-top: 10px;">
                  <Icons.LogoutOutlined />
                  <span style="margin-left: 10px;">退出</span>
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
      </div>
    </div>
    <div class="admin-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import * as Icons from '@ant-design/icons-vue'
import { useUserStore } from '@/store/user'
import { getUserMenus, type MenuItem } from '@/api/user'
import MenuItemRecursive from '@/components/MenuItemRecursive.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const menuList = ref<MenuItem[]>([])
const selectedKeys = ref<string[]>([])


// 常用图标列表（Ant Design Icons）
const commonIcons = [
  { name: 'dashboard', component: Icons.DashboardOutlined },
  { name: 'user', component: Icons.UserOutlined },
  { name: 'team', component: Icons.TeamOutlined },
  { name: 'appstore', component: Icons.AppstoreOutlined },
  { name: 'setting', component: Icons.SettingOutlined },
  { name: 'file-search', component: Icons.FileSearchOutlined },
  { name: 'thunderbolt', component: Icons.ThunderboltOutlined },
  { name: 'home', component: Icons.HomeOutlined },
  { name: 'folder', component: Icons.FolderOutlined },
  { name: 'file', component: Icons.FileOutlined },
  { name: 'database', component: Icons.DatabaseOutlined },
  { name: 'cloud', component: Icons.CloudOutlined },
  { name: 'lock', component: Icons.LockOutlined },
  { name: 'key', component: Icons.KeyOutlined },
  { name: 'safety', component: Icons.SafetyOutlined },
  { name: 'bar-chart', component: Icons.BarChartOutlined },
  { name: 'line-chart', component: Icons.LineChartOutlined },
  { name: 'pie-chart', component: Icons.PieChartOutlined },
  { name: 'table', component: Icons.TableOutlined },
  { name: 'form', component: Icons.FormOutlined },
  { name: 'edit', component: Icons.EditOutlined },
  { name: 'delete', component: Icons.DeleteOutlined },
  { name: 'search', component: Icons.SearchOutlined },
  { name: 'filter', component: Icons.FilterOutlined },
  { name: 'reload', component: Icons.ReloadOutlined },
  { name: 'download', component: Icons.DownloadOutlined },
  { name: 'upload', component: Icons.UploadOutlined },
  { name: 'export', component: Icons.ExportOutlined },
  { name: 'import', component: Icons.ImportOutlined },
  { name: 'printer', component: Icons.PrinterOutlined },
  { name: 'mail', component: Icons.MailOutlined },
  { name: 'phone', component: Icons.PhoneOutlined },
  { name: 'message', component: Icons.MessageOutlined },
  { name: 'notification', component: Icons.NotificationOutlined },
  { name: 'bell', component: Icons.BellOutlined },
  { name: 'calendar', component: Icons.CalendarOutlined },
  { name: 'clock-circle', component: Icons.ClockCircleOutlined },
  { name: 'tag', component: Icons.TagOutlined },
  { name: 'book', component: Icons.BookOutlined },
  { name: 'bookmark', component: Icons.BookOutlined },
  { name: 'file-text', component: Icons.FileTextOutlined },
  { name: 'link', component: Icons.LinkOutlined },
  { name: 'share-alt', component: Icons.ShareAltOutlined },
  { name: 'copy', component: Icons.CopyOutlined },
  { name: 'save', component: Icons.SaveOutlined },
  { name: 'eye', component: Icons.EyeOutlined },
  { name: 'eye-invisible', component: Icons.EyeInvisibleOutlined },
  { name: 'info-circle', component: Icons.InfoCircleOutlined },
  { name: 'question-circle', component: Icons.QuestionCircleOutlined },
  { name: 'check-circle', component: Icons.CheckCircleOutlined },
  { name: 'close-circle', component: Icons.CloseCircleOutlined },
  { name: 'warning', component: Icons.WarningOutlined },
  { name: 'menu', component: Icons.MenuOutlined },
  { name: 'unordered-list', component: Icons.UnorderedListOutlined },
  { name: 'ordered-list', component: Icons.OrderedListOutlined },
  { name: 'scan', component: Icons.ScanOutlined },
  { name: 'qrcode', component: Icons.QrcodeOutlined },
  { name: 'fund', component: Icons.FundOutlined },
  { name: 'dollar', component: Icons.DollarOutlined },
  { name: 'wallet', component: Icons.WalletOutlined },
  { name: 'bank', component: Icons.BankOutlined },
  { name: 'credit-card', component: Icons.CreditCardOutlined },
  { name: 'shopping', component: Icons.ShoppingOutlined },
  { name: 'shopping-cart', component: Icons.ShoppingCartOutlined },
  { name: 'gift', component: Icons.GiftOutlined },
  { name: 'trophy', component: Icons.TrophyOutlined },
  { name: 'star', component: Icons.StarOutlined },
  { name: 'heart', component: Icons.HeartOutlined },
  { name: 'fire', component: Icons.FireOutlined },
  { name: 'rocket', component: Icons.RocketOutlined },
  { name: 'bulb', component: Icons.BulbOutlined },
  { name: 'tool', component: Icons.ToolOutlined },
  { name: 'api', component: Icons.ApiOutlined },
  { name: 'code', component: Icons.CodeOutlined },
  { name: 'bug', component: Icons.BugOutlined },
  { name: 'github', component: Icons.GithubOutlined },
  { name: 'cloud-server', component: Icons.CloudServerOutlined },
  { name: 'desktop', component: Icons.DesktopOutlined },
  { name: 'laptop', component: Icons.LaptopOutlined },
  { name: 'mobile', component: Icons.MobileOutlined },
  { name: 'customer-service', component: Icons.CustomerServiceOutlined },
  { name: 'contacts', component: Icons.ContactsOutlined },
  { name: 'idcard', component: Icons.IdcardOutlined },
  { name: 'safety-certificate', component: Icons.SafetyCertificateOutlined },
  { name: 'verified', component: Icons.VerifiedOutlined }
]

// 获取图标组件
const getIcon = (iconName?: string) => {
  if (!iconName) return null
  const IconComponent = commonIcons.find(icon => icon.name === iconName.toLowerCase())?.component 
  return IconComponent || Icons.SettingOutlined
}


// 根据路由路径找到对应的菜单 code（递归查找）
const getMenuCodeFromPath = (path: string): string | null => {
  // 递归查找菜单项
  const findMenuCode = (menus: MenuItem[], targetPath: string): string | null => {
    for (const menu of menus) {
      // 检查路径是否匹配
      const menuPath = menu.path?.startsWith('/') ? menu.path : menu.path ? `/${menu.path}` : ''
      if (menuPath === targetPath || targetPath.startsWith(menuPath + '/')) {
        return menu.code
      }
      // 递归检查子菜单
      if (menu.children && menu.children.length > 0) {
        const childCode = findMenuCode(menu.children, targetPath)
        if (childCode) {
          return childCode
        }
      }
    }
    return null
  }
  
  return findMenuCode(menuList.value, path)
}

// 初始化选中状态
const updateSelectedKeys = () => {
  const path = route.path
  // 如果是主题设置页面
  if (path === '/admin/theme-settings') {
    selectedKeys.value = ['theme-settings']
    return
  }
  // 从菜单列表中查找匹配的 code
  const menuCode = getMenuCodeFromPath(path)
  if (menuCode) {
    selectedKeys.value = [menuCode]
  } else {
    // 如果找不到，尝试使用路由名称或路径的最后一段
    const pathSegments = path.split('/').filter(Boolean)
    const lastSegment = pathSegments[pathSegments.length - 1]
    selectedKeys.value = [lastSegment || (route.name as string)]
  }
}

// 获取用户菜单
const fetchUserMenus = async () => {
  try {
    const response = await getUserMenus()
    if (response.code === 200 && response.data) {
      menuList.value = response.data
      // 菜单加载后更新选中状态
      updateSelectedKeys()
    }
  } catch (error) {
    console.error('获取用户菜单失败:', error)
    message.error('获取菜单失败，请刷新页面重试')
  }
}

// 组件挂载时获取菜单
onMounted(() => {
  fetchUserMenus()
})

watch(
  () => route.path,
  () => {
    updateSelectedKeys()
  },
  { immediate: true }
)

// 监听菜单列表变化，更新选中状态
watch(
  () => menuList.value,
  () => {
    updateSelectedKeys()
  },
  { deep: true }
)


const handleMenuSelect = ({ key }: { key: string }) => {
  // 如果是主题设置，使用固定路径
  if (key === 'theme-settings') {
    router.push('/admin/theme-settings')
    return
  }

  // 递归查找菜单路径
  const findMenuPath = (menus: MenuItem[], code: string): string | null => {
    for (const menu of menus) {
      if (menu.code === code) {
        // 只返回有实际路径的菜单项（叶子节点）
        return menu.path || null
      }
      // 递归查找子菜单
      if (menu.children && menu.children.length > 0) {
        const childPath = findMenuPath(menu.children, code)
        if (childPath) return childPath
      }
    }
    return null
  }
  
  const menuPath = findMenuPath(menuList.value, key)
  if (menuPath) {
    // 如果路径是绝对路径（以 / 开头），直接使用
    const finalPath = menuPath.startsWith('/') ? menuPath : `/${menuPath}`
    router.push(finalPath)
  } else {
    // 如果找不到，使用默认路径
    router.push(`/${key}`)
  }
}

const handleMenuClick = ({ key }: { key: string }) => {
  switch (key) {
    case 'home':
      router.push('/home')
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
.admin-layout {
  display: flex;
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
      radial-gradient(circle at 10% 20%, rgba($accent-color, 0.06) 0%, transparent 50%),
      radial-gradient(circle at 90% 80%, rgba($primary-color, 0.05) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }
}

.admin-sidebar {
  width: $sidebar-width;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(250, 252, 255, 0.95) 100%);
  backdrop-filter: blur(10px);
  border-right: 1px solid rgba($primary-color, 0.1);
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  z-index: 5;

  .sidebar-header {
    padding: 20px 16px;
    border-bottom: 1px solid rgba($primary-color, 0.1);
    background: linear-gradient(90deg, rgba($primary-color, 0.03) 0%, transparent 100%);
    position: relative;

    &::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 16px;
      right: 16px;
      height: 1px;
      background: linear-gradient(90deg, transparent, $accent-color, transparent);
    }

    .system-title {
      font-size: 18px;
      font-weight: 600;
      background: linear-gradient(135deg, $text-primary 0%, $primary-color 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin: 0 0 8px 0;
    }

    .section-title {
      font-size: 14px;
      color: $text-secondary;
      font-weight: 500;
    }
  }

  .admin-menu {
    flex: 1;
    overflow-y: auto;
    border-right: none;

    :deep(.ant-menu-item-selected) {
      background: linear-gradient(90deg, rgba($primary-color, 0.1) 0%, rgba($accent-color, 0.05) 100%);
      color: $primary-color;
      border-left: 3px solid $primary-color;
      font-weight: 500;

      .anticon {
        color: $primary-color;
      }
    }

    :deep(.ant-menu-item:hover) {
      background: linear-gradient(90deg, rgba($primary-color, 0.06) 0%, rgba($accent-color, 0.03) 100%);
      color: $primary-color;
    }
  }

  .sidebar-footer {
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

    .user-info {
      @include flex-center;
      justify-content: flex-start;
      gap: 8px;
      padding: 8px 12px;
      color: $text-secondary;
      cursor: pointer;
      border-radius: 6px;
      transition: all 0.3s;

      .user-avatar :deep(.anticon) {
        color: $primary-color;
      }

      &:hover {
        background: linear-gradient(90deg, rgba($primary-color, 0.08) 0%, rgba($accent-color, 0.04) 100%);
        color: $primary-color;

        .user-avatar :deep(.anticon) {
          color: $primary-color;
        }
      }
    }
  }
}

.admin-content {
  flex: 1;
  overflow-y: auto;
  background: transparent;
  position: relative;
  z-index: 1;
}
</style>
