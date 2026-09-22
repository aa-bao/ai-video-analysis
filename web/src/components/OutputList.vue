<!-- 产物清单：解析完成后用户实际能拿到的东西。
     刻意不用卡片网格（与 FeatureGrid 的 3×2 拉开版式节拍），改为单块玻璃面板内的双列清单，
     对应参考项目 ComparisonSection「一块容器装一组对照信息」的构图。 -->
<template>
  <section class="section" aria-labelledby="output-heading">
    <SectionHead
      id="output-heading"
      title="解析完成后，"
      accent="这些产物各自可下载"
      hint="不需要二次整理，产出即成品。"
    />
    <div class="outputs glass-surface">
      <div v-for="item in OUTPUTS" :key="item.title" class="outputs__row">
        <span class="outputs__icon" aria-hidden="true">
          <el-icon><component :is="item.icon" /></el-icon>
        </span>
        <div class="outputs__body">
          <h3 class="outputs__title">{{ item.title }}</h3>
          <p class="outputs__text">{{ item.text }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ChatDotRound, Document, FolderOpened, Headset, Picture, VideoPlay } from '@element-plus/icons-vue'
import SectionHead from './SectionHead.vue'

const OUTPUTS = [
  { icon: VideoPlay, title: '视频文件', text: '解析完成后直接下载原画视频，无需跳转第三方站点。' },
  { icon: Headset, title: '音频文件', text: '抽出独立音轨，便于二次剪辑或与转录逐句核对。' },
  { icon: Picture, title: '关键帧图片', text: '按 8 / 12 / 24 张抽取，逐张可单独下载。' },
  { icon: Document, title: 'HTML 报告', text: '一键导出单文件报告，含转录、画面与结论。' },
  { icon: ChatDotRound, title: '转录与问答记录', text: '完整问答记录留在任务下，随时回看与继续追问。' },
  { icon: FolderOpened, title: '视频库归档', text: '所有任务统一入库，可检索、刷新与删除。' },
]
</script>

<style scoped>
.outputs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 32px;
  padding: 24px;
  border-radius: var(--radius-3xl);
  box-shadow: var(--shadow-card);
}

@media (max-width: 900px) {
  .outputs {
    grid-template-columns: minmax(0, 1fr);
    padding: 20px;
  }
}

.outputs__row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 0;
}

/* 图标徽标 = 36px 圆角方 + 主色 10% 透明底（规约 §2.7 / §7 基线） */
.outputs__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-lg);
  background: var(--accent-blue-soft);
  color: var(--accent-blue);
  font-size: 18px;
}

.outputs__body {
  min-width: 0;
}

.outputs__title {
  margin: 0 0 2px;
  font-size: var(--text-card);
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.outputs__text {
  margin: 0;
  font-size: var(--text-body);
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
