<!-- 使用步骤：三步流程（对应参考项目 HowToSection 的 `grid md:grid-cols-3` 构图）。
     步骤文案全部对应本页真实存在的操作入口，不写规划中能力（规约 §8.10 禁止伪功能）。 -->
<template>
  <section class="section" aria-labelledby="howto-heading">
    <SectionHead
      id="howto-heading"
      title="三步，"
      accent="把视频交给 AI"
      hint="全程不用离开当前页面，也不需要安装任何客户端。"
    />
    <ol class="howto">
      <li v-for="step in STEPS" :key="step.title" class="howto__item">
        <span class="howto__num" aria-hidden="true">{{ step.number }}</span>
        <h3 class="howto__title">{{ step.title }}</h3>
        <p class="howto__text">{{ step.text }}</p>
        <el-icon v-if="step.number < STEPS.length" class="howto__arrow" aria-hidden="true"><Right /></el-icon>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { Right } from '@element-plus/icons-vue'
import SectionHead from './SectionHead.vue'

const STEPS = [
  {
    number: 1,
    title: '粘贴链接或上传文件',
    text: '支持 bilibili、抖音、微信视频号、小红书图文链接，整段分享文案会自动提取地址；也可以直接上传本地视频或音频。',
  },
  {
    number: 2,
    title: '选关键帧与平台渠道',
    text: '默认抽取 12 张关键帧，可切换 8 / 24 张或纯音频；平台默认自动识别，识别不出时可在提交前手工指定。',
  },
  {
    number: 3,
    title: '看过程、拿产物、继续追问',
    text: '每一步解析过程实时展示；完成后可下载视频 / 音频 / 关键帧、导出 HTML 报告，并就转录与画面内容连续提问。',
  },
]
</script>

<style scoped>
.howto {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 28px;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 900px) {
  .howto {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
  }
}

.howto__item {
  position: relative;
  text-align: center;
}

/* 序号磁贴 = 56px 圆角方 + 主色 10% 透明底（规约 §7 图标徽标同一套语言） */
.howto__num {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  border-radius: var(--radius-3xl);
  background: var(--accent-blue-soft);
  color: var(--accent-blue);
  font-size: var(--text-h1);
  font-weight: 800;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.howto__title {
  margin: 0 0 8px;
  font-size: var(--text-card);
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.howto__text {
  margin: 0;
  font-size: var(--text-body);
  line-height: 1.5;
  color: var(--text-secondary);
}

/* 步骤之间的连接箭头：窄屏自动隐藏（规约 §6 不做纯 px 硬排） */
.howto__arrow {
  position: absolute;
  top: 22px;
  right: -20px;
  font-size: 18px;
  color: var(--text-tertiary);
}

@media (max-width: 900px) {
  .howto__arrow {
    display: none;
  }
}
</style>
