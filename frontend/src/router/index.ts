import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'

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
  } else {
    next()
  }
})

export default router
