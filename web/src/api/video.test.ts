import { describe, expect, it } from 'vitest'
import {
  agentAvatarUrl,
  frameUrl,
  libraryFrameUrl,
  libraryReportUrl,
  postImageUrl,
  reportUrl,
  taskAudioUrl,
  taskEventUrl,
  taskVideoUrl,
} from './video'

describe('task asset URLs', () => {
  it('roots every task asset under /api/video/tasks/<id>', () => {
    expect(frameUrl('t1', 'f.jpg')).toBe('/api/video/tasks/t1/frames/f.jpg')
    expect(postImageUrl('t1', 'p.png')).toBe('/api/video/tasks/t1/images/p.png')
    expect(reportUrl('t1')).toBe('/api/video/tasks/t1/report.html')
    expect(taskEventUrl('t1')).toBe('/api/video/tasks/t1/events')
  })

  it('appends ?download=1 only when a download is requested', () => {
    expect(taskVideoUrl('t1')).toBe('/api/video/tasks/t1/video')
    expect(taskVideoUrl('t1', true)).toBe('/api/video/tasks/t1/video?download=1')
    expect(taskAudioUrl('t1')).toBe('/api/video/tasks/t1/audio')
    expect(taskAudioUrl('t1', true)).toBe('/api/video/tasks/t1/audio?download=1')
  })

  it('keeps the archived-library namespace separate from live tasks', () => {
    expect(libraryFrameUrl('dir1', 'f.jpg')).toBe('/api/video/library/dir1/frames/f.jpg')
    expect(libraryReportUrl('dir1')).toBe('/api/video/library/dir1/report.html')
  })

  it('escapes a task directory that contains path separators', () => {
    expect(libraryFrameUrl('a/b', 'f.jpg')).toBe('/api/video/library/a%2Fb/frames/f.jpg')
  })

  it('points the agent avatar at the backend static endpoint', () => {
    expect(agentAvatarUrl()).toBe('/api/video/agent-avatar')
  })
})
