import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, PERMISSION_SETTINGS_MANAGE } from '../stores/auth'
import { canAccess } from './guard'
import { applicationBasePath } from '../platform'

const router = createRouter({
  history: createWebHistory(applicationBasePath()),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: '登录' },
    },
    {
      path: '/',
      component: () => import('../layouts/AppLayout.vue'),
      meta: { requiresAuth: true },
      redirect: '/video',
      children: [
        {
          path: 'video',
          name: 'video-analysis',
          component: () => import('../views/VideoAnalysisView.vue'),
          meta: { title: 'AI 视频分析' },
        },
        {
          path: 'video/library',
          name: 'video-library',
          component: () => import('../views/VideoLibraryView.vue'),
          meta: { title: '视频库' },
        },
        {
          path: 'settings/video',
          name: 'video-settings',
          component: () => import('../views/VideoSettingsView.vue'),
          meta: { title: 'AI 视频设置', permission: PERMISSION_SETTINGS_MANAGE },
        },
        {
          // 旧路径兼容：/video/settings → /settings/video
          path: 'video/settings',
          redirect: '/settings/video',
        },
        {
          path: 'settings/users',
          name: 'users',
          component: () => import('../views/UsersView.vue'),
          meta: { title: '用户管理', permission: PERMISSION_SETTINGS_MANAGE },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/video' },
  ],
})

router.beforeEach(async (to) => {
  // 阶段 5a：P2 独立部署，未登录回本地登录页，登录后进入 AI 视频分析。
  const auth = useAuthStore()
  if (!auth.initialized) {
    await auth.init()
  }
  if (to.name === 'login' && !auth.isGuest) {
    return { name: 'video-analysis' }
  }
  if (to.meta.requiresAuth && !auth.user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (auth.user && !canAccess(auth.user, to.meta)) {
    return { name: 'video-analysis' }
  }
})

export default router
