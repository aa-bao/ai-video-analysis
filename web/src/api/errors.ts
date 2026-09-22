/** 前端统一错误模型（阶段 6 · 方案 §11.7）。

后端错误体形如 `{ success: false, error: { code, message } }`；本模块把任意
`fetch` 抛出的原始体规整为带 `code` / `status` 的 `AppError`，并区分配额类错误
（访客配额超限：HTTP 403 + `VIDEO_QUOTA_EXCEEDED`，前端据此展示文案、绝不触发
401 整页跳登录）。
*/
export class AppError extends Error {
  /** 稳定错误码（如 VIDEO_QUOTA_EXCEEDED），前端据此区分错误类型 */
  code: string
  /** HTTP 状态码（尽量从响应透传；解析失败时为 0） */
  status: number

  constructor(code: string, message: string, status = 0) {
    super(message)
    this.name = 'AppError'
    this.code = code
    this.status = status
  }
}

/** 把任意错误（fetch 抛出的原始错误体 / 普通 Error / 已是 AppError）规整为 AppError。 */
export function toAppError(err: unknown, status = 0): AppError {
  if (err instanceof AppError) {
    // 已带状态码、而调用方这次给出了更权威的状态码时补上（否则保持原值）。
    return status > 0 && err.status === 0 ? new AppError(err.code, err.message, status) : err
  }
  const body = (err ?? {}) as {
    error?: { code?: string; message?: string }
    message?: string
    status?: number
  }
  const code = body.error?.code ?? 'UNKNOWN_ERROR'
  const message = body.error?.message ?? body.message ?? '请求失败'
  // [P6-P2-FIX5] 状态码必须由调用方显式透传：`fetch` 的响应体里没有 status 字段，
  // 只靠 `body.status` 会恒为 0（曾经如此），配额 403 / 会话 401 就分不出来。
  const fallbackStatus = typeof body.status === 'number' ? body.status : 0
  return new AppError(code, message, status > 0 ? status : fallbackStatus)
}

/** 是否为「访客配额超限」类错误（403，绝不触发 401 整页跳转）。 */
export function isQuotaError(err: unknown): boolean {
  return toAppError(err).code === 'VIDEO_QUOTA_EXCEEDED'
}
