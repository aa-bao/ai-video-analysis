import { afterEach, describe, expect, it } from 'vitest'
import { applicationBasePath, applicationUrl, sessionExpiredTarget } from './platform'

afterEach(() => {
  window.history.replaceState({}, '', '/')
})

describe('resource URLs are relative', () => {
  it('normalises a bare path to an application-absolute path', () => {
    window.history.replaceState({}, '', '/video')
    expect(applicationUrl('api/video/tasks')).toBe('/api/video/tasks')
    expect(applicationUrl('/api/video/tasks')).toBe('/api/video/tasks')
  })

  it('stays relative even if the page happens to sit under a mount prefix', () => {
    window.history.replaceState({}, '', '/project-apps/xxzw-video/video')
    expect(applicationUrl('/api/video/tasks')).toBe('/api/video/tasks')
  })

  it('passes absolute URLs through untouched', () => {
    expect(applicationUrl('https://cdn.example.com/a.png')).toBe('https://cdn.example.com/a.png')
  })
})

describe('application base path', () => {
  it('roots standalone deployments at the site root', () => {
    window.history.replaceState({}, '', '/video')
    expect(applicationBasePath()).toBe('/')
  })

  it('still detects a platform mount prefix for its own APP_KEY', () => {
    window.history.replaceState({}, '', '/project-apps/xxzw-video/video')
    expect(applicationBasePath()).toBe('/project-apps/xxzw-video/')
  })

  it('does not mistake another application key for its own prefix', () => {
    window.history.replaceState({}, '', '/project-apps/rag-database/video')
    expect(applicationBasePath()).toBe('/')
  })
})

describe('session expiry targets', () => {
  it('returns /login when the session expires off the login page', () => {
    window.history.replaceState({}, '', '/video')
    expect(sessionExpiredTarget()).toBe('/login')
  })

  it('returns null on the login page to avoid redirect loops', () => {
    window.history.replaceState({}, '', '/login')
    expect(sessionExpiredTarget()).toBe(null)
  })
})
