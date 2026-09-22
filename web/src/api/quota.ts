/** 访客配额（解析条数 + 单条时长上限）前端模型与展示辅助（阶段 6 · 方案 §11.7）。

键名与后端 `VisitorTaskQuota.snapshot()` 严格一致：
`tasks_used` / `tasks_max` / `max_duration_seconds`。账号登录时该快照为 `null`。
*/
export interface VisitorQuota {
  tasks_used: number
  tasks_max: number
  max_duration_seconds: number
}

/** 剩余可解析次数（封底为 0）。 */
export function quotaRemaining(q: VisitorQuota | null | undefined): number {
  if (!q) return 0
  return Math.max(0, q.tasks_max - q.tasks_used)
}

/** 单条时长上限（分钟）：后端以秒计，前端以分钟展示（如 1200s → 20 分钟）。 */
export function durationLimitMinutes(q: VisitorQuota | null | undefined): number {
  if (!q) return 20
  return Math.round(q.max_duration_seconds / 60)
}

/** 配额是否已耗尽（用于禁用提交按钮、提前拦截）。 */
export function isQuotaExhausted(q: VisitorQuota | null | undefined): boolean {
  if (!q) return false
  return q.tasks_used >= q.tasks_max
}

/** 访客配额的**唯一**展示文案：`单条上限 N 分钟 · 剩余 M/上限 次`。
 *
 * 方案 §11.5 要求「单条时长上限在提交前可见」；用户 2026-09-22 反馈原先
 * 「徽标说剩余条数、下面一行又说时长上限」是同一件事分两处讲，故合并成一条，
 * 由本函数统一生成（页面里只出现一次，见 VideoAnalysisView 的 Hero 状态徽标）。
 *
 * ⚠️ 计数是 ``rag_visitor.upload_count``，**累计值、不做每日重置**，故不写「今日」。
 */
export function guestQuotaHint(q: VisitorQuota | null | undefined): string {
  if (!q) return ''
  return `单条上限 ${durationLimitMinutes(q)} 分钟 · 剩余 ${quotaRemaining(q)}/${q.tasks_max} 次`
}
