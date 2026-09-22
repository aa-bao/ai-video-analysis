<!-- 任务列表（单一组件，两种落位）。
     原为 VideoAnalysisView 里的右侧抽屉，重构后「换位置」：
       · layout="grid" → 首页 Hero 下方的「最近的解析」区段（多列卡片）；
       · layout="rail" → 选中任务后工作区左侧的常驻任务栏（单列，边跑边切）。
     抽屉已删除：它盖住内容，且右上角触发点与居中 Hero 的构图不搭。
     卡片状态文案走 `utils/task-display`，与 AI 执行过程里的状态标签同源。 -->
<template>
  <ul class="task-list" :class="`task-list--${layout}`">
    <li v-if="!tasks.length" class="task-list__empty">{{ emptyText }}</li>
    <template v-else>
      <li
        v-for="task in tasks"
        :key="task.task_id"
        v-motion="cardMotion"
        class="task-card"
        :class="{ 'task-card--active': activeId === task.task_id }"
        role="button"
        tabindex="0"
        :aria-current="activeId === task.task_id ? 'true' : undefined"
        @click="emit('select', task)"
        @keydown.enter.prevent="emit('select', task)"
        @keydown.space.prevent="emit('select', task)"
      >
        <div class="task-card__main">
          <div class="task-card__source">
            <el-tag :type="task.kind === 'url' ? 'primary' : 'warning'" size="small">
              {{ taskKindLabel(task.kind) }}
            </el-tag>
            <span class="task-card__source-text" :title="task.source">
              {{ shortenSource(task.source) }}
            </span>
          </div>
          <div class="task-card__meta">
            <el-tag :type="taskStatusType(task.status)" size="small">
              {{ taskStatusLabel(task) }}
            </el-tag>
            <span class="task-card__time">{{ formatClock(task.created_at) }}</span>
            <span v-if="task.keyframes.length" class="task-card__frames">
              {{ task.keyframes.length }} 帧
            </span>
          </div>
        </div>
        <button
          class="task-card__delete"
          type="button"
          :title="`删除任务：${shortenSource(task.source, 24)}`"
          @click.stop="emit('remove', task.task_id)"
        >
          删除
        </button>
      </li>
    </template>
  </ul>
</template>

<script setup lang="ts">
import { useReducedMotion } from '@vueuse/motion'
import type { VideoTask } from '../api/video'
import { formatClock, shortenSource, taskKindLabel, taskStatusLabel, taskStatusType } from '../utils/task-display'

withDefaults(
  defineProps<{
    tasks: VideoTask[]
    /** 当前打开的任务 id（高亮用） */
    activeId?: string | null
    /** grid = 首页区段多列；rail = 工作区左侧单列 */
    layout?: 'grid' | 'rail'
    emptyText?: string
  }>(),
  { activeId: null, layout: 'rail', emptyText: '暂无解析任务' },
)

const emit = defineEmits<{
  select: [task: VideoTask]
  remove: [taskId: string]
}>()

// 减弱动态效果时去掉悬浮位移（规约 §6）；位移走弹簧，**不使用** CSS transition（规约 §4）
const reducedMotion = useReducedMotion()
const cardMotion = reducedMotion.value
  ? { initial: { y: 0 }, hovered: { y: 0 } }
  : { initial: { y: 0 }, hovered: { y: -2, transition: { type: 'spring', bounce: 0, duration: 0.4 } } }
</script>

<style scoped>
.task-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.task-list--rail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-list--grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.task-list__empty {
  padding: 32px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
}

.task-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-2xl);
  border: 1px solid var(--border-subtle);
  background: var(--bg-subtle);
  cursor: pointer;
}

.task-card:hover {
  border-color: color-mix(in srgb, var(--accent-blue) 35%, transparent);
}

.task-card--active {
  border-color: color-mix(in srgb, var(--accent-blue) 55%, transparent);
  background: color-mix(in srgb, var(--accent-blue) 6%, transparent);
}

.task-card__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-card__source {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-card__source-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-primary);
}

.task-card__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.task-card__time {
  font-variant-numeric: tabular-nums;
}

.task-card__frames {
  color: var(--text-secondary);
}

.task-card__delete {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-lg);
}

.task-card__delete:hover {
  color: var(--accent-red);
  background: color-mix(in srgb, var(--accent-red) 8%, transparent);
}
</style>
