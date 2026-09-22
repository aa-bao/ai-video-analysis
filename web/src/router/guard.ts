import type { AuthUser } from '../stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    /** 平台权限字符（规范 10 §8）：入口可见性以权限为准，不只做前端隐藏 */
    permission?: string
    /** 本地角色白名单（仅 LOCAL 模式，platform 权限优先） */
    roles?: string[]
    /** 页面标题（导航/面包屑用） */
    title?: string
  }
}

/**
 * 路由可达性（规范 10 §8：按钮/入口可见性必须与后端接口权限一致）：
 * 声明了 permission 时以平台权限字符为准；否则按本地角色白名单判断。
 */
export function canAccess(user: AuthUser, meta: { permission?: string; roles?: string[] }): boolean {
  if (meta.permission) {
    return (user.permissions ?? []).includes(meta.permission)
  }
  if (!meta.roles || meta.roles.length === 0) return true
  return meta.roles.includes(user.role)
}
