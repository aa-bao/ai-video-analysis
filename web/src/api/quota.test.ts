import { describe, expect, it } from 'vitest'
import {
  durationLimitMinutes,
  guestQuotaHint,
  isQuotaExhausted,
  quotaRemaining,
  type VisitorQuota,
} from './quota'

const sample: VisitorQuota = { tasks_used: 1, tasks_max: 5, max_duration_seconds: 1200 }

describe('guest quota helpers', () => {
  it('remaining = max - used', () => {
    expect(quotaRemaining(sample)).toBe(4)
  })

  it('duration limit in minutes (1200s -> 20min)', () => {
    expect(durationLimitMinutes(sample)).toBe(20)
  })

  it('exhausted when used >= max', () => {
    expect(isQuotaExhausted({ tasks_used: 5, tasks_max: 5, max_duration_seconds: 1200 })).toBe(true)
    expect(isQuotaExhausted(sample)).toBe(false)
  })

  // 该文案是页面上**唯一**的配额提示（不再与徽标各说一半），且不写「今日」
  // —— 后端 upload_count 是累计计数，没有每日重置。
  it('hint text shows duration and remaining in one line (方案 §11.5)', () => {
    expect(guestQuotaHint(sample)).toBe('单条上限 20 分钟 · 剩余 4/5 次')
  })

  it('hint text never claims a daily reset', () => {
    expect(guestQuotaHint(sample)).not.toContain('今日')
  })

  it('exhausted quota renders 剩余 0/5', () => {
    expect(guestQuotaHint({ tasks_used: 5, tasks_max: 5, max_duration_seconds: 1200 })).toBe(
      '单条上限 20 分钟 · 剩余 0/5 次',
    )
  })

  it('null quota yields empty hint and is never exhausted', () => {
    expect(guestQuotaHint(null)).toBe('')
    expect(isQuotaExhausted(null)).toBe(false)
    expect(quotaRemaining(null)).toBe(0)
    expect(durationLimitMinutes(null)).toBe(20)
  })
})
