import { describe, expect, it } from 'vitest'
import { AppError, isQuotaError, toAppError } from './errors'

describe('AppError', () => {
  it('carries code / message / status and is an Error', () => {
    const e = new AppError('X', 'msg', 403)
    expect(e.code).toBe('X')
    expect(e.message).toBe('msg')
    expect(e.status).toBe(403)
    expect(e).toBeInstanceOf(Error)
  })
})

describe('toAppError', () => {
  it('passes through an existing AppError', () => {
    const e = new AppError('A', 'b', 400)
    expect(toAppError(e)).toBe(e)
  })

  it('reads body.error.code / body.error.message (not top-level)', () => {
    const e = toAppError({
      success: false,
      error: { code: 'VIDEO_QUOTA_EXCEEDED', message: '访客最多可解析 5 条视频' },
    })
    expect(e).toBeInstanceOf(AppError)
    expect(e.code).toBe('VIDEO_QUOTA_EXCEEDED')
    expect(e.message).toBe('访客最多可解析 5 条视频')
  })

  it('falls back to top-level message when error is absent', () => {
    const e = toAppError({ success: false, message: 'plain failure' })
    expect(e.code).toBe('UNKNOWN_ERROR')
    expect(e.message).toBe('plain failure')
  })

  it('wraps a plain Error without losing its message', () => {
    const e = toAppError(new Error('boom'))
    expect(e.code).toBe('UNKNOWN_ERROR')
    expect(e.message).toBe('boom')
  })
})

describe('isQuotaError', () => {
  it('is true only for VIDEO_QUOTA_EXCEEDED', () => {
    expect(isQuotaError(new AppError('VIDEO_QUOTA_EXCEEDED', 'x', 403))).toBe(true)
    expect(
      isQuotaError({
        success: false,
        error: { code: 'VIDEO_QUOTA_EXCEEDED', message: '访客最多可解析 5 条视频' },
      }),
    ).toBe(true)
    expect(isQuotaError(new AppError('NOT_FOUND', 'x', 404))).toBe(false)
  })
})
