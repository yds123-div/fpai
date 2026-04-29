import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'
import { getUserMenus, type MenuItem } from '@/api/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/home',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'home',
        name: 'Home',
        component: () => import('@/views/home/index.vue'),
        meta: { title: '首页' }
      },
      {
        path: 'fpai/chat',
        name: 'FpaiChat',
        component: () => import('@/views/fpai/ChatView.vue'),
        meta: { title: '智能对话' }
      },
      {
        path: 'fpai/compare',
        name: 'FpaiCompare',
        component: () => import('@/views/fpai/CompareView.vue'),
        meta: { title: '产品对比' }
      },
      {
        path: 'fpai/recommend',
        name: 'FpaiRecommend',
        component: () => import('@/views/fpai/RecommendView.vue'),
        meta: { title: '产品推荐' }
      },
      {
        path: 'fpai/report',
        name: 'FpaiReport',
        component: () => import('@/views/fpai/ReportView.vue'),
        meta: { title: '报告生成' }
      },
      {
        path: 'fpai/evidence',
        name: 'FpaiEvidence',
        component: () => import('@/views/fpai/EvidenceView.vue'),
        meta: { title: '证据查询' }
      },
      {
        path: 'fpai/feedback',
        name: 'FpaiFeedback',
        component: () => import('@/views/fpai/FeedbackView.vue'),
        meta: { title: '回答反馈' }
      },
      {
        path: 'fpai/products',
        name: 'FpaiProducts',
        component: () => import('@/views/fpai/ProductsView.vue'),
        meta: { title: '产品列表' }
      },
      {
        path: 'fpai/knowledge',
        name: 'FpaiKnowledge',
        component: () => import('@/views/fpai/KnowledgeView.vue'),
        meta: { title: '知识库检索' }
      },
      {
        path: 'fpai/rm',
        name: 'FpaiRmWorkspace',
        component: () => import('@/views/fpai/RmWorkspaceView.vue'),
        meta: { title: 'RM工作台' }
      }
    ]
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, title: '后台管理' },
    children: [
      {
        path: 'system/user',
        name: 'UserManagement',
        component: () => import('@/views/admin/user/index.vue'),
        meta: { title: '用户管理' }
      },
      
      {
        path: 'system/config',
        name: 'ConfigManagement',
        component: () => import('@/views/admin/config/index.vue'),
        meta: { title: '系统参数管理' }
      },
      {
        path: 'system/roles',
        name: 'RoleManagement',
        component: () => import('@/views/admin/system/roles/index.vue'),
        meta: { title: '角色管理' }
      },
      {
        path: 'system/menus',
        name: 'MenuManagement',
        component: () => import('@/views/admin/system/menus/index.vue'),
        meta: { title: '菜单管理' }
      },
      {
        path: 'theme-settings',
        name: 'ThemeSettings',
        component: () => import('@/views/admin/theme-settings/index.vue'),
        meta: { title: '主题样式设置' }
      },
      {
        path: 'model',
        name: 'ModelManagement',
        component: () => import('@/views/admin/model/index.vue'),
        meta: { title: '模型管理' }
      },
      {
        path: 'knowledge',
        name: 'KnowledgeManagement',
        component: () => import('@/views/admin/knowledge/index.vue'),
        meta: { title: '知识库' }
      },
      {
        path: 'agent',
        name: 'AgentManagement',
        component: () => import('@/views/admin/agent/index.vue'),
        meta: { title: 'Agent管理' }
      },
      {
        path: 'skill',
        name: 'SkillManagement',
        component: () => import('@/views/admin/skill/index.vue'),
        meta: { title: 'Skill管理' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()

  if (to.meta.requiresAuth && !userStore.token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
  } else if (to.path === '/login' && userStore.token) {
    next({ path: '/' })
  } else if (to.path.startsWith('/admin')) {
    const roles = (userStore.userInfo as any)?.roles
    const isAdmin = Array.isArray(roles) && roles.map((x: any) => String(x).toLowerCase()).includes('admin')
    if (isAdmin) return next()

    // 非 admin：允许进入“有后台菜单权限”的页面
    // 后端菜单权限来自：/rbac/menus/me（由角色->菜单映射决定）
    const toPath = (to.path || '').replace(/\/+$/, '') || '/'
    const cacheKey = 'user_admin_menus'
    const now = Date.now()
    const cacheRaw = (sessionStorage.getItem(cacheKey) || '').trim()
    let cached: { ts: number; menus: MenuItem[] } | null = null
    if (cacheRaw) {
      try {
        cached = JSON.parse(cacheRaw) as { ts: number; menus: MenuItem[] }
      } catch {
        cached = null
      }
    }
    const ttlMs = 30_000

    const loadMenus = async () => {
      if (cached && (now - cached.ts) < ttlMs && Array.isArray(cached.menus)) {
        return cached.menus
      }
      const res = await getUserMenus()
      const menus = Array.isArray(res.data) ? res.data : []
      try {
        sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), menus }))
      } catch {
        // ignore
      }
      return menus
    }

    loadMenus()
      .then((menus) => {
        const normalizedMenus = (menus || []).filter((m) => (m.path || '').trim().length > 0)
        const allowed =
          toPath === '/admin' ||
          normalizedMenus.some((m) => {
            const menuPath = String(m.path || '').replace(/\/+$/, '')
            if (!menuPath) return false
            return toPath === menuPath || toPath.startsWith(menuPath + '/')
          })

        if (!allowed) next({ path: '/' })
        else next()
      })
      .catch(() => next({ path: '/' }))
  } else {
    next()
  }
})

export default router
