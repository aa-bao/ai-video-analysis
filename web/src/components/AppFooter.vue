<!-- 全站页脚（由 AppLayout 在 RouterView 之后渲染，随主内容区一起滚动）。
     构图取自 liyupi/free-video-downloader 的 AppFooter：居中关键词段落 → 分隔线 → 品牌 / 声明 / 版权三栏。
     差异：参考项目用锚点假链接，这里换成真实路由（规约 §8.10 禁止伪功能）。 -->
<template>
  <footer class="app-footer">
    <p class="app-footer__lead">
      <b>AI 视频解析</b> —— 粘贴 bilibili、抖音、微信视频号、小红书图文链接，或直接上传本地视频与音频，
      自动完成转写、关键帧抽取与内容问答，并产出可单独下载的视频、音频、关键帧与 HTML 报告。
    </p>

    <nav class="app-footer__links" aria-label="页脚导航">
      <RouterLink :to="{ name: 'video-analysis' }" class="app-footer__link">开始解析</RouterLink>
      <span class="app-footer__dot" aria-hidden="true"></span>
      <RouterLink :to="{ name: 'video-library' }" class="app-footer__link">视频库</RouterLink>
    </nav>

    <div class="app-footer__bottom">
      <span class="app-footer__brand">
        <span class="app-footer__logo" aria-hidden="true">
          <el-icon><VideoCamera /></el-icon>
        </span>
        AI 视频解析
      </span>
      <p class="app-footer__note">
        解析依赖外部模型服务完成转写与摘要，请勿提交涉密或未授权素材；下载内容的版权归原作者所有。
      </p>
      <span class="app-footer__copy">© {{ year }} AI 视频解析</span>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { VideoCamera } from '@element-plus/icons-vue'

const year = new Date().getFullYear()
</script>

<style scoped>
/* 页脚自带 24px 纵向内边距（横向上层 `.app-frame` 已不给，故这里自己补 24px），
   使页脚内层与页面内容、顶栏品牌落在同一条竖线上 */
.app-footer {
  flex-shrink: 0;
  margin-top: 40px;
  padding: 28px 24px 24px;
  border-top: 1px solid var(--border-subtle);
}

.app-footer__lead {
  max-width: 720px;
  margin: 0 auto 16px;
  font-size: var(--text-label);
  line-height: 1.7;
  text-align: center;
  color: var(--text-secondary);
}

.app-footer__lead b {
  font-weight: 650;
  color: var(--text-primary);
}

.app-footer__links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 20px;
}

.app-footer__link {
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--accent-blue);
  text-decoration: none;
}

.app-footer__link:hover {
  text-decoration: underline;
}

.app-footer__dot {
  width: 3px;
  height: 3px;
  border-radius: var(--radius-full);
  background: var(--text-tertiary);
}

.app-footer__bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.app-footer__brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.app-footer__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-lg);
  background: var(--accent-blue);
  color: var(--text-on-accent);
  font-size: 13px;
}

.app-footer__note {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.6;
  text-align: center;
  color: var(--text-tertiary);
}

.app-footer__copy {
  flex-shrink: 0;
  font-size: 11.5px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 900px) {
  .app-footer__bottom {
    flex-direction: column;
    align-items: center;
  }
}
</style>
