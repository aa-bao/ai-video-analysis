/** 任务展示辅助：状态标签 / 类型标签 / 来源缩写 / 时刻格式。
 *
 * **单一来源**：`components/TaskList.vue` 与 `views/VideoAnalysisView.vue` 都从这里取，
 * 避免「两处各写一份、改一处漏一处」的漂移（任务列表曾在抽屉里、后在左侧栏，两处的
 * 状态文案必须完全一致）。
 */
import type { VideoTask } from '../api/video'

/** 任务状态中文标签（列表 / 控制台状态标签共用） */
export function taskStatusLabel(task: VideoTask): string {
  if (task.status === 'complete') return '完成'
  if (task.status === 'failed') return '失败'
  if (task.status === 'running') return '解析中'
  return '排队中'
}

/** 任务状态 → el-tag 语义色（成功绿 / 失败红 / 进行中黄 / 待办灰） */
export function taskStatusType(
  status: string,
): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'complete') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

/** 任务来源类型标签 */
export function taskKindLabel(kind: VideoTask['kind']): string {
  return kind === 'url' ? '链接' : '文件'
}

/** 来源缩写：URL 很长，列表里截断显示，完整值靠 title 悬浮补足。
 *
 * 截断后总长**恰为 max**（省略号占 1 位），便于断言与排版估算。
 */
export function shortenSource(source: string, max = 40): string {
  if (source.length <= max) return source
  return source.slice(0, max - 1) + '…'
}

/** 时刻（HH:MM:SS）：任务创建时间与流水线日志时间共用 */
export function formatClock(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
