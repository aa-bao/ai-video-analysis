/**
 * 回归保护：ASR 渠道徽章/占位文案必须跟随 settings.asr_provider。
 *
 * 背景：曾把「火山引擎语音技术」与 bigmodel 占位**写死**在模板里，切到百炼渠道后
 * 仍显示火山品牌 → 管理员会以为配错了渠道。此文件锁死两条渠道的文案映射。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../api/video', () => ({
  getVideoEnv: vi.fn().mockResolvedValue({ pipeline: 'builtin', asr_configured: false }),
  getVideoSettings: vi.fn().mockResolvedValue({
    asr_provider: 'dashscope',
    asr_model: 'qwen-audio-3.1-asr-flash-filetrans',
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
  }),
  getVideoCookies: vi.fn().mockResolvedValue({
    douyin: { configured: false, path: '', cookie_count: 0, domains: [], updated_at: null },
    yuanbao: { configured: false, path: '', cookie_count: 0, domains: [], updated_at: null },
  }),
  testVideoSettings: vi.fn(),
  updateVideoSettings: vi.fn(),
  saveDouyinCookies: vi.fn(),
  saveYuanbaoCookies: vi.fn(),
}))

import VideoSettingsView from '../views/VideoSettingsView.vue'

const stubs = {
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { props: ['label'], template: '<div><slot /></div>' },
  // 必须真正实现 v-model，否则 form.asr_model 无法回显到 input.value
  'el-input': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-collapse': { template: '<div><slot /></div>' },
  'el-collapse-item': { template: '<div><slot /></div>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-select': { template: '<select><slot /></select>' },
  'el-option': { template: '<option />' },
  'el-switch': { template: '<input type="checkbox" />' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<label><slot /></label>' },
}

describe('VideoSettingsView · ASR 渠道跟随', () => {
  it('dashscope 渠道显示百炼品牌与千问占位，且不显示火山旧版入口', async () => {
    const wrapper = mount(VideoSettingsView, { global: { stubs } })
    // 等待 load() 的两处异步填充
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('阿里云百炼')
    })

    const text = wrapper.text()
    expect(text).toContain('阿里云百炼 · 通义千问')
    expect(text).not.toContain('火山引擎语音技术')
    // 百炼渠道不展示「旧版控制台 App ID + Access Token」（那是火山专有）
    expect(text).not.toContain('旧版控制台 App ID + Access Token')

    // 模型名由后端回填，不要被 bigmodel 覆盖
    const values = wrapper.findAll('input').map(i => (i.element as HTMLInputElement).value)
    expect(values).toContain('qwen-audio-3.1-asr-flash-filetrans')
    expect(values).not.toContain('bigmodel')

    // 百炼渠道须显式说明「音频怎么送进去」，避免再次误以为要公网入口
    expect(text).toContain('OSS 直传')
    expect(text).toContain('ASR_UPLOAD_MODE')
  })
})
