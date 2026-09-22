<!-- AI 视频设置：AI 视频解析的语音模型 / Chat 模型 / 解析偏好 / 运行环境 -->
<template>
  <div class="page settings-page">
    <header class="page__header">
      <h1 class="page__title">AI 视频设置</h1>
      <span class="page__subtitle">AI 视频解析的模型配置与环境信息</span>
    </header>

    <div class="settings-grid">
    <!-- 语音模型（ASR）—— 渠道由后端 .env 的 ASR_PROVIDER 决定，此处仅跟随展示 -->
    <section class="card glass-surface" aria-label="语音模型">
      <div class="card__head">
        <h2 class="card__title">语音模型（ASR）</h2>
        <span class="card__badge">{{ asrChannel.badge }}</span>
      </div>
      <el-form label-position="top" class="setting-form">
        <el-form-item label="模型名">
          <el-input v-model="form.asr_model" :placeholder="asrChannel.modelPlaceholder" />
        </el-form-item>
        <el-form-item :label="asrChannel.keyLabel">
          <el-input
            v-model="form.asr_api_key"
            type="password"
            show-password
            :placeholder="settings.has_asr_api_key ? '已配置（留空则不变）' : asrChannel.keyPlaceholder"
          />
        </el-form-item>
        <p v-if="asrChannel.isDashscope" class="field-hint">
          音频送入方式：<strong>OSS 直传</strong>（本地文件经百炼取临时凭证直传阿里云 OSS，
          无需本机公网可达；由 <code>ASR_UPLOAD_MODE</code> 控制）
        </p>
        <el-collapse v-if="!asrChannel.isDashscope" class="legacy-collapse">
          <el-collapse-item title="旧版控制台 App ID + Access Token（可选）">
            <el-form-item label="App ID">
              <el-input
                v-model="form.asr_app_id"
                :placeholder="settings.has_asr_app_id ? '已配置（留空则不变）' : '旧版控制台 APP ID'"
              />
            </el-form-item>
            <el-form-item label="Access Token">
              <el-input
                v-model="form.asr_access_token"
                type="password"
                show-password
                :placeholder="settings.has_asr_access_token ? '已配置（留空则不变）' : '旧版控制台 Access Token'"
              />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
        <div class="form-actions">
          <el-button class="btn-press" :loading="testingAsr" @click="testAsr">测试连接</el-button>
          <el-button type="primary" class="btn-press" :loading="saving" @click="saveSettings">保存设置</el-button>
        </div>
        <p v-if="asrTestMsg" class="test-result" :class="{ ok: asrTestOk, fail: !asrTestOk }">{{ asrTestMsg }}</p>
      </el-form>
    </section>

    <!-- Chat 模型 -->
    <section class="card glass-surface" aria-label="Chat 模型">
      <div class="card__head">
        <h2 class="card__title">Chat 模型（摘要 + 问答）</h2>
      </div>
      <p class="card__hint">摘要/解析与问答回复可分别配置 Base URL、模型名和 API Key；留空的字段会复用另一侧或系统配置。</p>

      <!-- 摘要/解析模型 -->
      <div class="model-block">
        <div class="model-block__head">
          <span class="model-block__title">摘要/解析模型</span>
        </div>
        <div class="model-block__body">
          <el-form :model="form" label-position="top" class="model-form">
            <el-form-item label="Base URL">
              <el-input v-model="form.chat_base_url" placeholder="https://ark.cn-beijing.volces.com/api/v3" clearable />
            </el-form-item>
            <el-form-item label="模型名">
              <el-input v-model="form.chat_model" placeholder="doubao-seed-2-1-pro-260628" clearable />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input
                v-model="form.chat_api_key"
                type="password"
                show-password
                :placeholder="settings.has_chat_api_key ? '已配置（留空则不变）' : '填写 API Key（空则复用系统）'"
                autocomplete="new-password"
              />
            </el-form-item>
          </el-form>
          <div class="model-block__test">
            <span class="model-block__result" :class="chatModelTestMsg ? (chatModelTestOk ? 'model-block__result--ok' : 'model-block__result--fail') : ''">
              <span v-if="chatModelTestMsg">{{ chatModelTestMsg }}</span>
            </span>
            <el-button class="btn-press" :loading="testingChatModel" @click="testChatModel">
              测试模型
            </el-button>
          </div>
        </div>
      </div>

      <!-- 问答回复模型 -->
      <div class="model-block">
        <div class="model-block__head">
          <span class="model-block__title">问答回复模型</span>
        </div>
        <div class="model-block__body">
          <el-form :model="form" label-position="top" class="model-form">
            <el-form-item label="Base URL">
              <el-input v-model="form.qa_base_url" placeholder="留空则与摘要模型共用" clearable />
            </el-form-item>
            <el-form-item label="模型名">
              <el-input v-model="form.qa_model" placeholder="doubao-seed-2-1-turbo-260628" clearable />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input
                v-model="form.qa_api_key"
                type="password"
                show-password
                :placeholder="settings.has_qa_api_key ? '已配置（留空则不变）' : '留空则与摘要模型共用'"
                autocomplete="new-password"
              />
            </el-form-item>
          </el-form>
          <div class="model-block__test">
            <span class="model-block__result" :class="qaModelTestMsg ? (qaModelTestOk ? 'model-block__result--ok' : 'model-block__result--fail') : ''">
              <span v-if="qaModelTestMsg">{{ qaModelTestMsg }}</span>
            </span>
            <el-button class="btn-press" :loading="testingQaModel" @click="testQaModel">
              测试模型
            </el-button>
          </div>
        </div>
      </div>

      <div class="card__actions">
        <el-button type="primary" class="btn-press" :loading="saving" @click="saveSettings">保存设置</el-button>
      </div>
    </section>

    <!-- 解析偏好 -->
    <section class="card glass-surface" aria-label="解析偏好">
      <div class="card__head">
        <h2 class="card__title">解析偏好</h2>
        <el-button text size="small" class="card__reset btn-press" @click="resetDefaults">恢复默认</el-button>
      </div>
      <el-form label-position="top" class="setting-form pref-form">
        <el-form-item label="默认关键帧数量">
          <el-radio-group v-model="form.frames">
            <el-radio-button :value="0">纯音频</el-radio-button>
            <el-radio-button :value="8">8 帧</el-radio-button>
            <el-radio-button :value="12">12 帧（推荐）</el-radio-button>
            <el-radio-button :value="24">24 帧</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <div class="form-actions">
          <el-button type="primary" class="btn-press" :loading="saving" @click="saveSettings">保存设置</el-button>
        </div>
      </el-form>
    </section>

    <!-- Cookie 设置 -->
    <section class="card glass-surface cookie-card" aria-label="Cookie 设置">
      <div class="card__head">
        <h2 class="card__title">Cookie 设置</h2>
        <span class="card__badge">抖音 / 元宝</span>
      </div>
      <p class="card__hint">在线更新解析所需平台 Cookie；保存后直接写入共享文件，接口不展示 Cookie 明文。</p>

      <div class="cookie-grid">
        <div class="cookie-block">
          <div class="cookie-block__head">
            <span class="cookie-block__title">抖音 Cookie</span>
            <el-tag size="small" :type="cookieStatus.douyin.configured ? 'success' : 'info'">
              {{ cookieStatus.douyin.configured ? '已配置' : '未配置' }}
            </el-tag>
          </div>
          <div class="cookie-block__status">
            <span>Cookie 数：{{ cookieStatus.douyin.cookie_count }}</span>
            <span>域名：{{ cookieStatus.douyin.domains.length ? cookieStatus.douyin.domains.join('、') : '—' }}</span>
            <span>更新时间：{{ cookieStatus.douyin.updated_at || '—' }}</span>
          </div>
          <el-input
            v-model="douyinCookieText"
            type="textarea"
            :rows="6"
            placeholder="粘贴 Netscape 格式 Cookie（含 # Netscape HTTP Cookie File 头或 douyin.com 域名行）"
            class="cookie-textarea"
          />
          <div class="cookie-block__actions">
            <el-button
              class="btn-press"
              :loading="extractingDouyinCookie"
              @click="extractDouyinCookie"
            >
              从本机浏览器一键更新
            </el-button>
            <el-button type="primary" class="btn-press" :loading="savingDouyinCookie" @click="saveDouyinCookie">
              保存抖音 Cookie
            </el-button>
          </div>
          <p v-if="extractMsg" class="test-result" :class="{ ok: extractOk, fail: !extractOk }">
            {{ extractMsg }}
          </p>
          <p class="cookie-block__hint">
            「一键更新」读取本机 Chrome / Edge 已登录的抖音 Cookie（只读，不改浏览器文件）。
            ⚠️ Chrome 127+ 的 v20 App-Bound 加密无法自动解密，届时请改用手动粘贴。
          </p>
        </div>

        <div class="cookie-block">
          <div class="cookie-block__head">
            <span class="cookie-block__title">元宝 Cookie</span>
            <el-tag size="small" :type="cookieStatus.yuanbao.configured ? 'success' : 'info'">
              {{ cookieStatus.yuanbao.configured ? '已配置' : '未配置' }}
            </el-tag>
          </div>
          <div class="cookie-block__status">
            <span>Cookie 数：{{ cookieStatus.yuanbao.cookie_count }}</span>
            <span>域名：{{ cookieStatus.yuanbao.domains.length ? cookieStatus.yuanbao.domains.join('、') : '—' }}</span>
            <span>更新时间：{{ cookieStatus.yuanbao.updated_at || '—' }}</span>
          </div>
          <el-input
            v-model="yuanbaoCookieText"
            type="textarea"
            :rows="6"
            placeholder="粘贴 F12 请求头 Cookie（name=value; name2=value2）"
            class="cookie-textarea"
          />
          <div class="cookie-block__actions">
            <el-button type="primary" class="btn-press" :loading="savingYuanbaoCookie" @click="saveYuanbaoCookie">
              保存元宝 Cookie
            </el-button>
          </div>
        </div>
      </div>
    </section>

    <!-- 运行环境 -->
    <section class="card glass-surface" aria-label="运行环境">
      <div class="card__head">
        <h2 class="card__title">运行环境</h2>
      </div>
      <dl class="info-list">
        <div class="info-row"><dt>流水线</dt><dd>内置原生流水线（不依赖外部脚本）</dd></div>
        <div class="info-row"><dt>Python 解释器</dt><dd>{{ env.python || '—' }}</dd></div>
        <div class="info-row"><dt>视频数据库目录</dt><dd>{{ env.library_root || '—' }}</dd></div>
        <div class="info-row"><dt>任务输出目录</dt><dd>{{ env.output_root || '—' }}</dd></div>
        <div class="info-row"><dt>ASR 就绪</dt><dd>{{ env.asr_configured ? '已配置' : '未配置' }}</dd></div>
      </dl>
    </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getVideoCookies,
  getVideoEnv,
  getVideoSettings,
  saveDouyinCookies,
  extractDouyinCookies,
  saveYuanbaoCookies,
  testVideoSettings,
  updateVideoSettings,
  type VideoCookies,
  type VideoEnvInfo,
  type VideoSettings,
} from '../api/video'

const env = ref<VideoEnvInfo>({})
const settings = ref<VideoSettings>({
  asr_provider: 'volcengine',
  asr_model: 'bigmodel',
  has_asr_api_key: false,
  has_asr_app_id: false,
  has_asr_access_token: false,
  chat_base_url: '',
  chat_model: '',
  has_chat_api_key: false,
  qa_model: '',
  qa_base_url: '',
  has_qa_api_key: false,
  frames: 12,
})

const form = reactive({
  asr_model: 'bigmodel',
  asr_api_key: '',
  asr_app_id: '',
  asr_access_token: '',
  chat_base_url: '',
  chat_model: '',
  chat_api_key: '',
  qa_model: '',
  qa_base_url: '',
  qa_api_key: '',
  frames: 12,
})

// ASR 渠道展示：后端 ASR_PROVIDER 决定实际走哪条（.env 控制，前端只读跟随）。
// 曾把「火山引擎语音技术」写死在徽章里，切到百炼后仍显示火山，会误导。
const DASHSCOPE_ALIASES = ['dashscope', 'qwen', 'aliyun', 'bailian', 'aliyun-bailian']
const asrChannel = computed(() => {
  const provider = (settings.value.asr_provider || 'volcengine').toLowerCase()
  const isDashscope = DASHSCOPE_ALIASES.includes(provider)
  return isDashscope
    ? {
        isDashscope,
        badge: '阿里云百炼 · 通义千问',
        modelPlaceholder: 'qwen-audio-3.1-asr-flash-filetrans',
        keyLabel: 'API Key（百炼 DashScope）',
        keyPlaceholder: '填写百炼 API Key（sk- 开头）',
      }
    : {
        isDashscope,
        badge: '火山引擎语音技术',
        modelPlaceholder: 'bigmodel（录音文件极速识别）',
        keyLabel: 'API Key（新版控制台）',
        keyPlaceholder: '填写火山引擎语音技术 API Key',
      }
})

const saving = ref(false)
const testingAsr = ref(false)
const asrTestMsg = ref('')
const asrTestOk = ref(false)
const testingChatModel = ref(false)
const chatModelTestMsg = ref('')
const chatModelTestOk = ref(false)
const testingQaModel = ref(false)
const qaModelTestMsg = ref('')
const qaModelTestOk = ref(false)

const cookieStatus = ref<VideoCookies>({
  douyin: { configured: false, path: '', cookie_count: 0, domains: [], updated_at: null },
  yuanbao: { configured: false, path: '', cookie_count: 0, domains: [], updated_at: null },
})
const douyinCookieText = ref('')
const yuanbaoCookieText = ref('')
const savingDouyinCookie = ref(false)
const extractingDouyinCookie = ref(false)
const extractMsg = ref('')
const extractOk = ref(false)
const savingYuanbaoCookie = ref(false)

async function load() {
  try {
    const [envData, settingsData] = await Promise.all([getVideoEnv(), getVideoSettings()])
    env.value = envData
    settings.value = settingsData
    // 渠道决定回落默认值：百炼渠道别回落到 bigmodel（那是火山的模型名）
    form.asr_model = settingsData.asr_model || (asrChannel.value.isDashscope
      ? 'qwen-audio-3.0-asr-flash-filetrans'
      : 'bigmodel')
    form.frames = settingsData.frames ?? 12
    form.chat_base_url = settingsData.chat_base_url || ''
    form.chat_model = settingsData.chat_model || ''
    form.qa_model = settingsData.qa_model || ''
    form.qa_base_url = settingsData.qa_base_url || ''
    form.asr_api_key = ''
    form.asr_app_id = ''
    form.asr_access_token = ''
    form.chat_api_key = ''
    form.qa_api_key = ''
  } catch (err) {
    ElMessage.error((err as { message?: string })?.message || '加载设置失败')
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const updated = await updateVideoSettings({
      asr_model: form.asr_model.trim(),
      asr_api_key: form.asr_api_key,
      asr_app_id: form.asr_app_id,
      asr_access_token: form.asr_access_token,
      chat_base_url: form.chat_base_url.trim(),
      chat_model: form.chat_model.trim(),
      chat_api_key: form.chat_api_key,
      qa_model: form.qa_model.trim(),
      qa_base_url: form.qa_base_url.trim(),
      qa_api_key: form.qa_api_key,
      frames: form.frames,
    })
    settings.value = updated
    form.asr_api_key = ''
    form.asr_app_id = ''
    form.asr_access_token = ''
    form.chat_api_key = ''
    form.qa_api_key = ''
    asrTestMsg.value = ''
    chatModelTestMsg.value = ''
    qaModelTestMsg.value = ''
    ElMessage.success('设置已保存')
  } catch (err) {
    ElMessage.error((err as { message?: string })?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function testAsr() {
  testingAsr.value = true
  asrTestMsg.value = ''
  try {
    const res = await testVideoSettings({
      mode: 'asr',
      asr_model: form.asr_model.trim() || undefined,
      asr_api_key: form.asr_api_key || undefined,
      asr_app_id: form.asr_app_id || undefined,
      asr_access_token: form.asr_access_token || undefined,
    })
    asrTestOk.value = res.ok
    asrTestMsg.value = res.message || (res.ok ? '连接成功' : '连接失败')
  } catch (err) {
    asrTestOk.value = false
    asrTestMsg.value = (err as { message?: string })?.message || '测试失败'
  } finally {
    testingAsr.value = false
  }
}

async function testChatModel() {
  testingChatModel.value = true
  chatModelTestMsg.value = ''
  try {
    const res = await testVideoSettings({
      mode: 'chat_summary',
      chat_base_url: form.chat_base_url.trim() || undefined,
      chat_model: form.chat_model.trim() || undefined,
      chat_api_key: form.chat_api_key || undefined,
    })
    chatModelTestOk.value = res.ok
    chatModelTestMsg.value = res.message || (res.ok ? '连接成功' : '连接失败')
  } catch (err) {
    chatModelTestOk.value = false
    chatModelTestMsg.value = (err as { message?: string })?.message || '测试失败'
  } finally {
    testingChatModel.value = false
  }
}

async function testQaModel() {
  testingQaModel.value = true
  qaModelTestMsg.value = ''
  try {
    const res = await testVideoSettings({
      mode: 'chat_qa',
      chat_base_url: form.chat_base_url.trim() || undefined,
      chat_model: form.chat_model.trim() || undefined,
      chat_api_key: form.chat_api_key || undefined,
      qa_base_url: form.qa_base_url.trim() || undefined,
      qa_model: form.qa_model.trim() || undefined,
      qa_api_key: form.qa_api_key || undefined,
    })
    qaModelTestOk.value = res.ok
    qaModelTestMsg.value = res.message || (res.ok ? '连接成功' : '连接失败')
  } catch (err) {
    qaModelTestOk.value = false
    qaModelTestMsg.value = (err as { message?: string })?.message || '测试失败'
  } finally {
    testingQaModel.value = false
  }
}

function getErrorMessage(err: unknown, fallback: string): string {
  const candidate = err as { error?: { message?: string }; message?: string }
  return candidate.error?.message || candidate.message || fallback
}

async function loadCookieStatus() {
  try {
    cookieStatus.value = await getVideoCookies()
  } catch (err) {
    ElMessage.error(getErrorMessage(err, '加载 Cookie 状态失败'))
  }
}

async function saveDouyinCookie() {
  const content = douyinCookieText.value.trim()
  if (!content) {
    ElMessage.warning('请先粘贴抖音 Cookie')
    return
  }
  savingDouyinCookie.value = true
  try {
    const updated = await saveDouyinCookies(content)
    cookieStatus.value = { ...cookieStatus.value, douyin: updated }
    douyinCookieText.value = ''
    ElMessage.success('抖音 Cookie 已保存')
  } catch (err) {
    ElMessage.error(getErrorMessage(err, '保存抖音 Cookie 失败'))
  } finally {
    savingDouyinCookie.value = false
  }
}

async function extractDouyinCookie() {
  extractingDouyinCookie.value = true
  extractMsg.value = ''
  try {
    const r = await extractDouyinCookies()
    cookieStatus.value = { ...cookieStatus.value, douyin: r }
    extractOk.value = true
    const src = r.source ? `（来源 ${r.source}）` : ''
    extractMsg.value = `已从浏览器导出并写入 ${r.cookie_count} 条抖音 Cookie${src}`
    ElMessage.success('抖音 Cookie 已更新')
  } catch (err) {
    extractOk.value = false
    // 后端把「v20 加密解不开」等真实原因放在 message 里，原样展示比笼统报错有用
    extractMsg.value = getErrorMessage(err, '自动导出失败')
    ElMessage.error('自动导出失败，请改用手动粘贴')
  } finally {
    extractingDouyinCookie.value = false
  }
}

async function saveYuanbaoCookie() {
  const cookie = yuanbaoCookieText.value.trim()
  if (!cookie) {
    ElMessage.warning('请先粘贴元宝 Cookie')
    return
  }
  savingYuanbaoCookie.value = true
  try {
    const updated = await saveYuanbaoCookies(cookie)
    cookieStatus.value = { ...cookieStatus.value, yuanbao: updated }
    yuanbaoCookieText.value = ''
    ElMessage.success('元宝 Cookie 已保存')
  } catch (err) {
    ElMessage.error(getErrorMessage(err, '保存元宝 Cookie 失败'))
  } finally {
    savingYuanbaoCookie.value = false
  }
}

function resetDefaults() {
  form.frames = 12
}

onMounted(() => {
  load()
  loadCookieStatus()
})
</script>

<style scoped>
/* 页面根容器：滚动归 .app-main（AppLayout），这里只负责内边距与撑高 */
.page {
  padding: 24px;
}

.page__header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.page__title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--text-primary);
}

.page__subtitle {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.settings-page {
  overflow-y: auto;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  align-items: start;
  max-width: 1080px;
  margin: 0 auto;
}

.settings-grid .card {
  margin-bottom: 0;
  min-width: 0;
  padding: 18px 20px;
  border-radius: var(--radius-2xl);
}

.card__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.card__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.card__badge {
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
}

.card__hint {
  margin: -4px 0 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-tertiary);
}

.cookie-card {
  grid-column: 1 / -1;
}

.cookie-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.cookie-block {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--text-primary) 2%, transparent);
}

.cookie-block__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.cookie-block__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.cookie-block__status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-bottom: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.cookie-textarea {
  width: 100%;
}

.cookie-textarea :deep(.el-textarea__inner) {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
}

.cookie-block__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.cookie-block__hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

@media (max-width: 600px) {
  .cookie-grid {
    grid-template-columns: 1fr;
  }
}

.setting-form {
  max-width: 100%;
}

.model-block {
  margin-bottom: 20px;
}

.model-block:last-of-type {
  margin-bottom: 16px;
}

.model-block__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.model-block__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.model-block__body {
  display: flex;
  align-items: flex-end;
  gap: 16px;
}

.model-block__body .model-form {
  flex: 1;
  min-width: 0;
}

.model-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.model-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.model-form :deep(.el-form-item__label) {
  font-size: 12px;
  color: var(--text-secondary);
}

.model-block__test {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding-bottom: 2px;
}

.model-block__result {
  display: block;
  font-size: 12px;
  max-width: 220px;
  min-height: 16px;
  line-height: 16px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.model-block__result--ok {
  color: var(--accent-green);
}

.model-block__result--fail {
  color: var(--accent-red);
}

@media (max-width: 600px) {
  .model-block__body {
    flex-direction: column;
    align-items: stretch;
  }

  .model-form {
    grid-template-columns: 1fr;
  }
}

.pref-form {
  max-width: 100%;
}

.pref-form .el-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

.card__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}

.test-result {
  margin: 12px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
}

.test-result.ok {
  color: var(--accent-green);
}

.test-result.fail {
  color: var(--accent-red);
}

.field-hint {
  margin: -2px 0 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.field-hint code {
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  background: var(--surface-subtle, rgba(127, 127, 127, 0.12));
}

.legacy-collapse {
  margin: -6px 0 10px;
  border: none;
  --el-collapse-header-bg-color: transparent;
  --el-collapse-content-bg-color: transparent;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 4px 0 8px;
}

.info-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
  font-size: 13.5px;
}

.info-row dt {
  width: 160px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.info-row dd {
  margin: 0;
  color: var(--text-primary);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12.5px;
  word-break: break-all;
}
</style>
