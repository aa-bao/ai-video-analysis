import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import type { VisitorQuota } from '../api/quota'

export interface AuthUser {
  id: number | string
  username: string
  role: string
  /** 平台权限字符（本地模式按角色推导，与后端 /api/auth/me 一致） */
  permissions: string[]
  /** 是否平台身份（TEST/PRODUCTION 或挂载平台会话） */
  platform: boolean
  /** 是否免登录访客（阶段 6） */
  is_guest?: boolean
  /** 访客配额快照；账号为 null */
  quota?: VisitorQuota | null
}

export const ADMIN_ROLE = 'account_admin'

/** 平台权限字符（与 rpa-application.yaml / 后端 principal 一致） */
export const PERMISSION_SETTINGS_MANAGE = 'rag-database:settings:manage'
export const PERMISSION_KB_MANAGE = 'rag-database:knowledge-base:manage'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const loading = ref(false)
  const initialized = ref(false)
  // 阶段 6：免登录访客标记与配额快照
  const isGuest = ref(false)
  const quota = ref<VisitorQuota | null>(null)

  /**
   * 管理入口可见性（规范 10 §8）：以平台权限字符为准；
   * 本地模式回退到 account_admin 角色（与后端推导一致）。
   */
  const isAdmin = computed(
    () =>
      user.value?.role === ADMIN_ROLE ||
      (user.value?.permissions ?? []).includes(PERMISSION_SETTINGS_MANAGE),
  )

  function hasPermission(permission: string): boolean {
    return (user.value?.permissions ?? []).includes(permission)
  }

  function applyProfile(data: AuthUser): void {
    user.value = {
      ...data,
      permissions: data.permissions ?? [],
      platform: data.platform ?? false,
    }
    isGuest.value = !!data.is_guest
    quota.value = data.quota ?? null
  }

  async function init() {
    try {
      const resp = await api.me()
      applyProfile(resp.data)
    } catch {
      user.value = null
      isGuest.value = false
      quota.value = null
    } finally {
      initialized.value = true
    }
  }

  async function login(username: string, password: string) {
    await api.login(username, password)
    // 登录响应不含权限字符，登录成功后刷新完整资料（me 返回权限，规范 10 §8）
    const resp = await api.me()
    applyProfile(resp.data)
  }

  async function logout() {
    await api.logout()
    user.value = null
    isGuest.value = false
    quota.value = null
  }

  return { user, loading, initialized, isGuest, quota, isAdmin, hasPermission, init, login, logout }
})
