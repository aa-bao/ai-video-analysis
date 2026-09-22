import { describe, expect, it } from 'vitest'
import type { VideoTask } from '../api/video'
import {
  formatClock,
  shortenSource,
  taskKindLabel,
  taskStatusLabel,
  taskStatusType,
} from './task-display'

/** 最小可用任务对象：只覆盖本模块读到的字段 */
function task(patch: Partial<VideoTask> = {}): VideoTask {
  return {
    task_id: 't1',
    source: 'https://example.com/a.mp4',
    kind: 'url',
    status: 'submitted',
    created_at: '2026-09-22T10:20:30',
    updated_at: '2026-09-22T10:20:30',
    output_dir: null,
    error: null,
    stage: null,
    report: null,
    transcript: null,
    keyframes: [],
    cost: null,
    summary: null,
    ...patch,
  }
}

describe('task display helpers', () => {
  // 列表卡片与 AI 执行过程的状态标签共用这两个函数，映射必须逐条锁定
  it('maps every task status to a label', () => {
    expect(taskStatusLabel(task({ status: 'submitted' }))).toBe('排队中')
    expect(taskStatusLabel(task({ status: 'running' }))).toBe('解析中')
    expect(taskStatusLabel(task({ status: 'complete' }))).toBe('完成')
    expect(taskStatusLabel(task({ status: 'failed' }))).toBe('失败')
  })

  it('maps every task status to an el-tag type', () => {
    expect(taskStatusType('submitted')).toBe('info')
    expect(taskStatusType('running')).toBe('warning')
    expect(taskStatusType('complete')).toBe('success')
    expect(taskStatusType('failed')).toBe('danger')
  })

  it('labels the task source kind', () => {
    expect(taskKindLabel('url')).toBe('链接')
    expect(taskKindLabel('file')).toBe('文件')
  })

  it('shortens long sources but keeps short ones intact', () => {
    expect(shortenSource('https://example.com/a.mp4')).toBe('https://example.com/a.mp4')
    const long = 'a'.repeat(60)
    const cut = shortenSource(long)
    expect(cut.length).toBe(40)
    expect(cut.endsWith('…')).toBe(true)
    // 删除按钮的悬浮标题用更短的上限（默认 40 → 传 24）
    expect(shortenSource(long, 24).length).toBe(24)
  })

  it('formats a clock time and degrades safely', () => {
    expect(formatClock('2026-09-22T10:20:30')).toBe('10:20:30')
    expect(formatClock(null)).toBe('')
    // 非法时间原样返回，不抛错（老任务里存在非 ISO 字段）
    expect(formatClock('not-a-date')).toBe('not-a-date')
  })
})
