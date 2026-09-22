<!-- 能力概览：6 张能力卡片（3×2 固定网格）。
     原为 VideoAnalysisView 内联区段，重构时抽出为独立区段组件（内容零改动，仅补区段头节奏）。
     悬浮位移由 `cardMotion` 弹簧驱动，**不使用** CSS transition（规约 §4 红线）。 -->
<template>
  <section class="section" aria-labelledby="feature-heading">
    <SectionHead
      id="feature-heading"
      title="从一条链接，"
      accent="到一份能追问的文稿"
      hint="六件事一次做完，解析过程全程可见。"
    />
    <div class="feature-grid">
      <article v-for="f in FEATURES" :key="f.title" v-motion="cardMotion" class="card glass-surface feature-card">
        <span class="feature-card__icon" aria-hidden="true">
          <el-icon><component :is="f.icon" /></el-icon>
        </span>
        <h3 class="feature-card__title">{{ f.title }}</h3>
        <p class="feature-card__text">{{ f.text }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ChatDotRound, Document, Film, FolderOpened, Link, Microphone } from '@element-plus/icons-vue'
import { useReducedMotion } from '@vueuse/motion'
import SectionHead from './SectionHead.vue'

const FEATURES = [
  { icon: Link, title: '多平台解析', text: '粘贴链接或整段分享文案自动提取地址并识别平台，无需手工选择。' },
  { icon: Microphone, title: '语音转写', text: '优先复用平台字幕；无字幕时走 ASR 分片转写，并给出成本估算。' },
  { icon: Film, title: '关键帧与画面理解', text: '按需抽取 8 / 12 / 24 张关键帧，并结合画面内容补充视觉洞察。' },
  { icon: ChatDotRound, title: '视频问答', text: '基于真实转录与画面内容多轮追问，回答尽量标注 [MM:SS] 出处。' },
  { icon: Document, title: '报告与导出', text: '一键生成 HTML 报告，视频、音频与关键帧均可单独下载。' },
  { icon: FolderOpened, title: '视频库沉淀', text: '已解析任务统一入库，可检索、回看、刷新与删除。' },
]

// 减弱动态效果时去掉悬浮位移，只保留阴影变化（规约 §6）
const reducedMotion = useReducedMotion()
const cardMotion = reducedMotion.value
  ? { initial: { y: 0 }, hovered: { y: 0 } }
  : { initial: { y: 0 }, hovered: { y: -2, transition: { type: 'spring', bounce: 0, duration: 0.4 } } }
</script>

<style scoped>
/* 网格固定 3×2，避免 auto-fit 在宽屏排成 4+2 留空位 */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}

@media (max-width: 1100px) {
  .feature-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .feature-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.feature-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 0;
  padding: 20px;
}

/* 悬浮只换阴影：描边不透明度不变、不放大、不改底色（规约 §4.5） */
.feature-card:hover {
  box-shadow: var(--shadow-card-hover);
}

/* 图标徽标 = 32px 圆角方 + 主色 10% 透明底 + currentColor 图标（规约 §2.7 / §7 基线） */
.feature-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-lg);
  background: var(--accent-blue-soft);
  color: var(--accent-blue);
  font-size: 18px;
}

.feature-card__title {
  margin: 0;
  font-size: var(--text-card);
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.feature-card__text {
  margin: 0;
  font-size: var(--text-body);
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
