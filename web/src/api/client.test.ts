import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { redirectToSessionExpiry } from '../platform'
import { api } from './client'

// 只替换跳转副作用，applicationUrl 仍走真实实现（本文件要验它拼出的 URL）。
vi.mock('../platform', async () => {
  const actual = await vi.importActual<typeof import('../platform')>('../platform')
  return { ...actual, redirectToSessionExpiry: vi.fn() }
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fetchMock = vi.fn()

/**
 * 每次 fetch 都返回**新的** Response。
 * ⚠️ 不能写成 `fetchMock.mockResolvedValue(jsonResponse(...))` ——
 * 那样所有调用共用同一个 Response，而 Response body 只能读一次，
 * 第二次 `resp.json()` 会抛 `TypeError: Body is unusable`。
 */
function respondWith(body: unknown, status = 200): void {
  fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(body, status)))
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.mocked(redirectToSessionExpiry).mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('request plumbing', () => {
  it('prefixes /api, sends same-origin credentials and a JSON content type', async () => {
    respondWith({ success: true, data: { ok: 1 } })

    const res = await api.get('/video/tasks')

    expect(res.data).toEqual({ ok: 1 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/video/tasks')
    expect(init.credentials).toBe('same-origin')
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' })
  })

  it('serialises bodies for post/put/patch and omits an undefined body', async () => {
    respondWith({ success: true, data: null })

    await api.post('/video/tasks', { source: 'https://example.test/v' })
    await api.put('/video/settings', { frames: 12 })
    await api.patch('/video/settings', { frames: 6 })
    await api.post('/video/tasks/t1/qa')

    expect(fetchMock.mock.calls.map((c) => [c[0], c[1].method, c[1].body])).toEqual([
      ['/api/video/tasks', 'POST', JSON.stringify({ source: 'https://example.test/v' })],
      ['/api/video/settings', 'PUT', JSON.stringify({ frames: 12 })],
      ['/api/video/settings', 'PATCH', JSON.stringify({ frames: 6 })],
      ['/api/video/tasks/t1/qa', 'POST', undefined],
    ])
  })

  it('throws an AppError carrying the backend code/message/status when the response is not ok', async () => {
    // [P6-P2-FIX5] 阶段 6 起非 2xx 抛的是统一 AppError（读 body.error.{code,message}），
    // 不再是 fetch 的原始响应体 —— 旧的 `rejects.toEqual(errorBody)` 断言已随之更新。
    const errorBody = { success: false, error: { code: 'NOT_FOUND', message: '任务不存在' } }
    respondWith(errorBody, 404)

    await expect(api.get('/video/tasks/missing')).rejects.toMatchObject({
      name: 'AppError',
      code: 'NOT_FOUND',
      message: '任务不存在',
      status: 404,
    })
  })

  it('does not set a content type for multipart uploads', async () => {
    respondWith({ success: true, data: { path: 'p' } })
    const form = new FormData()

    await api.upload('/video/tasks/upload', form)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/video/tasks/upload')
    expect(init.body).toBe(form)
    expect(init.headers).toBeUndefined()
  })

  it('returns the raw response from queryRaw so SSE consumers can stream it', async () => {
    const raw = new Response('data: {}\n\n', { status: 200 })
    fetchMock.mockImplementation(() => Promise.resolve(raw))

    const got = await api.queryRaw('/video/tasks/t1/qa/stream', { question: 'q' })

    expect(got).toBe(raw)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/video/tasks/t1/qa/stream')
    expect(init.body).toBe(JSON.stringify({ question: 'q' }))
  })
})

describe('session expiry handling', () => {
  it('redirects on a 401 from a normal endpoint', async () => {
    respondWith({ success: false, error: { code: 'UNAUTHORIZED', message: 'x' } }, 401)

    await expect(api.get('/video/tasks')).rejects.toBeTruthy()

    expect(redirectToSessionExpiry).toHaveBeenCalledTimes(1)
  })

  it('does not redirect on the login endpoint own 401 (wrong password)', async () => {
    respondWith({ success: false, error: { code: 'INVALID_CREDENTIALS', message: 'x' } }, 401)

    await expect(api.login('someone', 'wrong')).rejects.toBeTruthy()

    expect(redirectToSessionExpiry).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/login')
  })
})

describe('identity endpoints', () => {
  it('exposes login / logout / me on the /auth surface', async () => {
    respondWith({ success: true, data: null })

    await api.login('u', 'p')
    await api.logout()
    respondWith({
      success: true,
      data: { id: 1, username: 'u', role: 'admin', permissions: [], platform: false },
    })
    await api.me()

    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/auth/login',
      '/api/auth/logout',
      '/api/auth/me',
    ])
  })
})
