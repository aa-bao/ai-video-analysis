<template>
  <main class="login-page">
    <!-- 整页背景：16:9 图片铺满（import 经 Vite 打包） -->
    <div class="login-page__bg" aria-hidden="true"></div>
    <!-- 整页浅色遮罩：保证两侧文字可读，同时保留图片视觉 -->
    <div class="login-page__shade" aria-hidden="true"></div>

    <!-- ══ 左侧品牌展示区（65%）：内容叠在背景图上 ══ -->
    <section class="login-hero">
      <!-- 内容 -->
      <div class="login-hero__content">
        <div class="login-hero__brand" v-motion="heroMotion(0)">
          <span class="login-hero__logo" aria-hidden="true">AI 工作台</span>
          <span class="login-hero__brand-name">xxzw-video</span>
        </div>

        <div class="login-hero__headline" v-motion="heroMotion(1)">
          <h1 class="login-hero__title">
            AI 视频解析 Agent<br />
            转录、抽帧与摘要，一站完成
          </h1>
          <p class="login-hero__subtitle">
            提交视频链接或本地文件，自动完成下载、字幕与语音转写、
            关键帧抽取与摘要，输出转录、关键帧与 HTML 报告。
          </p>
        </div>

        <div class="login-hero__stats" v-motion="heroMotion(2)">
          <div class="login-hero__stat">
            <span class="login-hero__stat-num kpi-num">100%</span>
            <span class="login-hero__stat-label">本地私有化部署</span>
          </div>
          <div class="login-hero__stat">
            <span class="login-hero__stat-num kpi-num">异步</span>
            <span class="login-hero__stat-label">长任务后台执行</span>
          </div>
          <div class="login-hero__stat">
            <span class="login-hero__stat-num kpi-num">结构化</span>
            <span class="login-hero__stat-label">转录·关键帧·摘要</span>
          </div>
        </div>

        <p class="login-hero__footer" v-motion="heroMotion(3)">
          © 2026 AI 工作台 · 企业智能工作平台
        </p>
      </div>
    </section>

    <!-- ══ 右侧登录区（35%）：白底 ══ -->
    <section class="login-form" aria-label="登录">
      <div class="login-form__inner" v-motion="formMotion">
        <p class="login-form__eyebrow">欢迎回来</p>
        <h2 class="login-form__title">登录你的账户</h2>
        <p class="login-form__subtitle">登录以使用 AI 视频解析</p>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="login-form__fields"
          @submit.prevent="handleLogin"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="输入用户名"
              size="large"
              :prefix-icon="User"
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="输入密码"
              size="large"
              show-password
              :prefix-icon="Lock"
              autocomplete="current-password"
            />
          </el-form-item>

          <el-alert
            v-if="error"
            :title="error"
            type="error"
            :closable="false"
            class="login-form__error"
          />

          <el-button
            type="primary"
            size="large"
            :loading="loading"
            native-type="submit"
            class="login-form__btn btn-press"
          >
            登录
          </el-button>
        </el-form>

        <p class="login-form__hint">账号由系统管理员统一分配，如有问题请联系管理员</p>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const error = ref('')

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

/* ── 动效：弹簧错峰进入（规范 4.4） ── */
function heroMotion(i: number) {
  return {
    initial: { y: 16, opacity: 0 },
    enter: {
      y: 0,
      opacity: 1,
      delay: 0.1 + i * 0.12,
      transition: { type: 'spring', bounce: 0, duration: 0.4 },
    },
  }
}

const formMotion = {
  initial: { x: 16, opacity: 0 },
  enter: {
    x: 0,
    opacity: 1,
    delay: 0.2,
    transition: { type: 'spring', bounce: 0, duration: 0.4 },
  },
}

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/chat')
  } catch {
    error.value = '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  min-height: 100vh;
  background: var(--bg-elevated);
  overflow: hidden;
}

/* 整页背景图片：16:9 cover 铺满 */
.login-page__bg {
  position: absolute;
  inset: 0;
  background-image: url('../assets/login-hero.png');
  background-size: cover;
  background-position: center;
  pointer-events: none;
  z-index: 0;
}

/* 整页浅色遮罩：保证文字可读，同时保留图片视觉 */
.login-page__shade {
  position: absolute;
  inset: 0;
  background: rgba(245, 245, 247, 0.55);
  backdrop-filter: blur(1px);
  -webkit-backdrop-filter: blur(1px);
  pointer-events: none;
  z-index: 1;
}

/* ═══════════ 左侧品牌区（65%） ═══════════ */
.login-hero {
  position: relative;
  z-index: 2;
  flex: 0 0 65%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-hero__content {
  max-width: 560px;
  padding: 48px;
  display: flex;
  flex-direction: column;
  gap: 40px;
}

.login-hero__brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.login-hero__logo {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--text-primary);
}

.login-hero__brand-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.login-hero__title {
  font-size: 40px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.25;
  color: var(--text-primary);
  margin-bottom: 20px;
}

.login-hero__subtitle {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-secondary);
  max-width: 420px;
}

/* 数据亮点 */
.login-hero__stats {
  display: flex;
  gap: 48px;
}

.login-hero__stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.login-hero__stat-num {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--accent-blue);
}

.login-hero__stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.login-hero__footer {
  margin-top: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ═══════════ 右侧登录区（35%） ═══════════ */
.login-form {
  position: relative;
  z-index: 2;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  /* 不透明白色背景：与左侧图片区形成硬分隔 */
  background: var(--bg-elevated);
  border-left: 1px solid var(--border-subtle);
}

.login-form__inner {
  width: 100%;
  max-width: 400px;
}

.login-form__eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent-blue);
  margin-bottom: 8px;
}

.login-form__title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.login-form__subtitle {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  margin-bottom: 32px;
}

.login-form__fields :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.login-form__error {
  margin-bottom: 16px;
}

.login-form__btn {
  width: 100%;
  height: 46px;
  margin-top: 8px;
  font-size: 15px;
}

.login-form__hint {
  margin-top: 24px;
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}

/* 窄屏：左侧隐藏，仅登录表单 */
@media (max-width: 900px) {
  .login-hero {
    display: none;
  }
  .login-form {
    padding: 32px;
  }
}
</style>
