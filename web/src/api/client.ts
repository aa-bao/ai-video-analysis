import { applicationUrl, redirectToSessionExpiry } from '../platform'
import { toAppError } from './errors'

export interface ApiResponse<T = unknown> {
  success: boolean
  data: T
  error?: { code: string; message: string }
}

class Client {
  private endpoint(url: string): string {
    return applicationUrl(`api${url}`)
  }

  /**
   * 会话过期（401）统一处理：一律回 `/login`。
   * 登录接口自身的 401（密码错误）不触发跳转；不向 URL 写入任何错误信息或 token。
   */
  private redirectOnUnauthorized(requestUrl: string): void {
    if (requestUrl.includes('/auth/login')) return
    redirectToSessionExpiry()
  }

  private async request<T>(url: string, init?: RequestInit): Promise<ApiResponse<T>> {
    const resp = await fetch(this.endpoint(url), {
      ...init,
      credentials: 'same-origin' as RequestCredentials,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (resp.status === 401) this.redirectOnUnauthorized(url)
    const body = await resp.json()
    if (!resp.ok) {
      // [P6-P2-FIX5] 透传 HTTP 状态码（403 配额 / 401 会话据此区分）
      throw toAppError(body, resp.status)
    }
    return body
  }

  get<T>(url: string) {
    return this.request<T>(url)
  }

  post<T>(url: string, data?: unknown) {
    return this.request<T>(url, {
      method: 'POST',
      body: data === undefined ? undefined : JSON.stringify(data),
    })
  }

  put<T>(url: string, data?: unknown) {
    return this.request<T>(url, {
      method: 'PUT',
      body: data === undefined ? undefined : JSON.stringify(data),
    })
  }

  patch<T>(url: string, data?: unknown) {
    return this.request<T>(url, {
      method: 'PATCH',
      body: data === undefined ? undefined : JSON.stringify(data),
    })
  }

  delete<T>(url: string) {
    return this.request<T>(url, { method: 'DELETE' })
  }

  async upload<T>(url: string, form: FormData): Promise<ApiResponse<T>> {
    const resp = await fetch(this.endpoint(url), {
      method: 'POST',
      credentials: 'same-origin',
      body: form,
    })
    if (resp.status === 401) this.redirectOnUnauthorized(url)
    const body = await resp.json()
    if (!resp.ok) {
      // [P6-P2-FIX5] 透传 HTTP 状态码（403 配额 / 401 会话据此区分）
      throw toAppError(body, resp.status)
    }
    return body
  }

  /** SSE 查询：返回原始 Response，由调用方用 streamSse 消费 */
  async queryRaw(url: string, body: unknown): Promise<Response> {
    const resp = await fetch(this.endpoint(url), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (resp.status === 401) this.redirectOnUnauthorized(url)
    return resp
  }

  async login(username: string, password: string) {
    return this.request<{ id: number; username: string; role: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  }

  async logout() {
    return this.request<null>('/auth/logout', { method: 'POST' })
  }

  async me() {
    return this.request<{
      id: number | string
      username: string
      role: string
      permissions: string[]
      platform: boolean
      is_guest: boolean
      quota: { tasks_used: number; tasks_max: number; max_duration_seconds: number } | null
    }>('/auth/me')
  }
}

export const api = new Client()
