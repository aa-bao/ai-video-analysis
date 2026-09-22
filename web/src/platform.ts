export const APP_KEY = 'xxzw-video'

/**
 * 应用挂载根。
 *
 * P2 从 `xxzw-rag` 切出时沿用了这个函数，目的是让 `router` 的 base 口径不变。
 * 独立部署下页面挂在站点根，故返回 `/`。
 *
 * `APP_KEY` 仅用于识别「被挂在平台子路径下」的历史形态
 * （`/project-apps/<APP_KEY>/`）。P2 自建独立项目后该形态不成立，
 * 因而本函数恒返回 `/`；将来上自有域名时可直接收敛为字面量。
 */
export function applicationBasePath(pathname = window.location.pathname): string {
  const marker = `/${APP_KEY}/`
  const markerIndex = pathname.indexOf(marker)
  if (markerIndex < 0) return '/'
  return pathname.slice(0, markerIndex + marker.length)
}

/**
 * 资源 URL —— 返回**相对路径**。
 *
 * P2 独立部署，不需要推断 origin；已是绝对 URL 的入参
 * （例如后端可能返回的完整外链）原样返回。
 */
export function applicationUrl(path: string): string {
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(path)) return path
  return path.startsWith('/') ? path : `/${path}`
}

/**
 * 401 会话过期的跳转目标：一律回 `/login`；
 * 已在登录页则返回 null（避免刷新循环）。
 */
export function sessionExpiredTarget(): string | null {
  if (window.location.pathname === '/login') return null
  return '/login'
}

/** 会话过期统一处理：按 sessionExpiredTarget 导航；无目标（已在登录页）则不动作。 */
export function redirectToSessionExpiry(): void {
  const target = sessionExpiredTarget()
  if (target) window.location.assign(target)
}
