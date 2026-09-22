<!-- 区段头：居中标题（可带主色尾缀）+ 一行说明。
     版式取自 liyupi/free-video-downloader 的 FeatureSection / HowToSection 构图
     （`text-center mb-12` + 标题内 `<span class="text-primary">`），
     样式落在全局 `.section-head*`（style.css），保证各页区段节拍一致。 -->
<template>
  <header class="section-head">
    <h2 :id="id" class="section-head__title">
      {{ title }}<span v-if="accent" class="section-head__accent">{{ accent }}</span>
    </h2>
    <p v-if="hint" class="section-head__hint">{{ hint }}</p>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  /** 供外层 `<section aria-labelledby>` 引用，保证区段有可读标题 */
  id: string
  title: string
  /** 标题尾缀（主色），对应参考项目标题里高亮的那半句 */
  accent?: string
  hint?: string
}>()
</script>
