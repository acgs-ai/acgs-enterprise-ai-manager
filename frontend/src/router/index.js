import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { sanitizeReturnTo } from '@/auth/returnTo'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Dashboard',
      component: () => import('@/views/Dashboard.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue')
    },
    {
      path: '/callback',
      name: 'Callback',
      component: () => import('@/views/Callback.vue')
    },
    {
      path: '/tasks',
      name: 'Tasks',
      component: () => import('@/views/Tasks.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/assets',
      name: 'Assets',
      component: () => import('@/views/Assets.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/infrastructure',
      name: 'Infrastructure',
      component: () => import('@/views/Infrastructure.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/projects',
      name: 'Projects',
      component: () => import('@/views/Projects.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/financial',
      name: 'Financial',
      component: () => import('@/views/Financial.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/documents',
      name: 'Documents',
      component: () => import('@/views/Documents.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

// Navigation guard for authentication
router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.init()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { path: '/login', query: { returnTo: to.fullPath } }
  }
  if (to.path === '/login' && authStore.isAuthenticated) {
    return sanitizeReturnTo(to.query.returnTo)
  }
})

export default router
