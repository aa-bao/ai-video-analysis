<!-- 应用外壳：顶部横向导航（玻璃条）+ 居中 70% 主内容区 + 全站页脚。
     导航壳形态参考 liyupi/free-video-downloader 的 AppHeader（左品牌 / 中纯文字导航 / 右账号区），
     独立部署项目不再需要左侧导航栏，故 AppLayout 为「header + frame + footer」。
     滚动归属：**由 `.app-main` 统一滚动**（页脚要随内容走），页面根容器只负责内边距。
     视觉基线：《前端页面设计规范.md》（Apple 玻璃拟态，令牌唯一，弹簧物理）。 -->
<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header__inner">
        <!-- 品牌区 -->
        <RouterLink :to="{ name: 'video-analysis' }" class="app-header__brand" title="AI 视频解析">
          <span class="app-header__logo" aria-hidden="true">
            <el-icon><VideoCamera /></el-icon>
          </span>
          <span class="app-header__brand-name">AI 视频解析</span>
          <span class="app-header__badge">免登录可用</span>
        </RouterLink>

        <!-- 主导航：纯文字 + 底部指示条（参考项目 nav 形态），管理入口按权限隐藏 -->
        <nav class="app-header__nav" aria-label="主导航">
          <RouterLink
            v-for="item in navItems"
            :key="item.name"
            :to="{ name: item.name }"
            class="app-header__nav-item btn-press"
            :class="{ 'app-header__nav-item--active': isActive(item.name) }"
            :aria-current="isActive(item.name) ? 'page' : undefined"
          >
            {{ item.label }}
          </RouterLink>
        </nav>

        <!-- 账号区：头像 + 下拉菜单 -->
        <div class="app-header__user">
          <el-dropdown v-if="auth.user" trigger="click" placement="bottom-end">
            <button class="app-header__user-btn btn-press" type="button" aria-label="账号菜单">
              <span class="app-header__avatar" aria-hidden="true">
                <img
                  v-if="!avatarBroken && !isGuest"
                  class="app-header__avatar-img"
                  :src="avatarImg"
                  alt=""
                  @error="avatarBroken = true"
                />
                <el-icon v-else class="app-header__avatar-icon"><component :is="isGuest ? UserFilled : User" /></el-icon>
              </span>
              <span class="app-header__user-meta">
                <span class="app-header__username">{{ displayName }}</span>
                <span class="app-header__role">{{ roleLabel }}</span>
              </span>
              <el-icon class="app-header__caret" aria-hidden="true"><ArrowDown /></el-icon>
            </button>

            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <span class="app-header__menu-note">{{ menuNote }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="quotaNote" disabled>
                  <span class="app-header__menu-note">{{ quotaNote }}</span>
                </el-dropdown-item>
                <!-- 访客**不提供**「退出 / 清空」：访客额度绑在访客会话上，清掉
                     Cookie 会换出一个新访客 = 额度刷回满格（后端 /api/auth/logout
                     对访客同样已 403）。访客要换身份 → 去登录页登录账号，登录后
                     账号身份优先、访客额度原样保留。 -->
                <el-dropdown-item divided @click="handleMenuAction">
                  <el-icon><SwitchButton /></el-icon>
                  {{ isGuest ? '登录管理员账号' : '退出登录' }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <RouterLink v-else :to="{ name: 'login' }" class="app-header__login btn-press">登录</RouterLink>
        </div>
      </div>
    </header>

    <!-- 主内容区 = 全站唯一滚动容器（页脚随内容一起滚） -->
    <main ref="mainRef" class="app-main">
      <div class="app-frame">
        <RouterView />
        <AppFooter />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, SwitchButton, User, UserFilled, VideoCamera } from '@element-plus/icons-vue'
import AppFooter from '../components/AppFooter.vue'
import { useAuthStore } from '../stores/auth'
import { guestQuotaHint } from '../api/quota'
import avatarImg from '../assets/avatar.jpg'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

interface NavItem {
  name: string
  label: string
  /** 仅管理员可见 */
  adminOnly?: boolean
}

/** 导航项：管理项只在管理员身份下出现（与后端权限一致） */
const ALL_NAV_ITEMS: NavItem[] = [
  { name: 'video-analysis', label: 'AI 视频分析' },
  { name: 'video-library', label: '视频库' },
  { name: 'video-settings', label: 'AI 视频设置', adminOnly: true },
  { name: 'users', label: '用户管理', adminOnly: true },
]

const navItems = computed(() => ALL_NAV_ITEMS.filter((item) => !item.adminOnly || auth.isAdmin))

function isActive(name: string): boolean {
  return route.name === name
}

const isGuest = computed(() => auth.isGuest)

/** 头像图加载失败时回退为首字母/图标占位 */
const avatarBroken = ref(false)

/** 访客不暴露 `v:<uuid>` 影子账号名，统一显示为「访客」。 */
const displayName = computed(() => {
  if (isGuest.value) return '访客'
  return auth.user?.username ?? '未登录'
})

const roleLabel = computed(() => {
  if (isGuest.value) return '免登录体验'
  return auth.isAdmin ? '管理员' : '成员'
})

const menuNote = computed(() => {
  // 访客不再暴露影子账号的数字 id（对本机用户没有意义），改为说明额度归属
  if (isGuest.value) return '免登录访客 · 额度随本机累计'
  return `账号：${auth.user?.username ?? '-'}`
})

const quotaNote = computed(() => {
  const text = guestQuotaHint(auth.quota)
  return isGuest.value && text ? text : ''
})

/** 滚动归属改为 `.app-main` 后，路由切换不再天然回到顶部，需显式重置 */
const mainRef = ref<HTMLElement | null>(null)

watch(
  () => route.fullPath,
  () => {
    mainRef.value?.scrollTo({ top: 0 })
  },
)

/** 账号菜单动作。
 *
 * 访客 → 只跳登录页，**不清空**访客会话（原先这里会 `logout()` + `location.reload()`，
 * 等于把访客额度刷满，已删）；账号 → 正常退出后回登录页。
 */
async function handleMenuAction() {
  if (isGuest.value) {
    router.push({ name: 'login' })
    return
  }
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<style scoped>
/* 版心宽度：桌面主口径 70%（用户口径 2026-09-21），窄屏两档降级，见文末媒体查询 */
.app-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  /* 页面主背景：设计令牌 --bg-base（规约 §2.1，全局唯一背景色） */
  background: var(--bg-base);
}

/* 主内容区背景环境光：两枚弥散光斑（规约 §5.2：blur 120px、全圆角、pointer-events none，
   颜色只引用 --glow-blue / --glow-violet）。
   挂在外壳而非 `.app-main` 上：`.app-main` 是滚动容器，绝对定位的光斑会随内容滚走。 */
.app-shell::before,
.app-shell::after {
  content: '';
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border-radius: var(--radius-full);
  filter: blur(120px);
}

.app-shell::before {
  top: -14%;
  left: 2%;
  width: 46vw;
  height: 46vw;
  max-width: 720px;
  max-height: 720px;
  background: var(--glow-blue);
}

.app-shell::after {
  top: 14%;
  right: 0;
  width: 38vw;
  height: 38vw;
  max-width: 600px;
  max-height: 600px;
  background: var(--glow-violet);
}

/* ── 顶部导航条：Apple 玻璃 ── */
.app-header {
  position: relative;
  z-index: 20;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-glass);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
}

/* 顶栏内层与主内容区同宽同轴：品牌、导航、账号区与页面内容左右对齐。
   24px 横向内边距 = 规约 §2.6 的「页面主区边距」，使 brand 与 .page 内容首行同一条竖线。 */
.app-header__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  height: 64px;
  width: 70%;
  padding: 0 24px;
  margin: 0 auto;
}

/* ── 品牌区 ── */
.app-header__brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  text-decoration: none;
  color: inherit;
}

/* 品牌磁贴：实底主色（规约 §1 禁止 AI 味渐变），圆角与卡片同曲率 */
.app-header__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-lg);
  background: var(--accent-blue);
  color: var(--text-on-accent);
  box-shadow: var(--shadow-card);
}

.app-header__logo .el-icon {
  font-size: 17px;
}

.app-header__brand-name {
  font-size: 15.5px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.app-header__badge {
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--accent-blue-soft);
  color: var(--accent-blue);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

/* ── 主导航：纯文字 + 底部 2px 指示条（参考项目 nav 形态）──
   规约 §4：交互位移一律弹簧，禁止 CSS transition；此处只做即时换色，
   激活态用静态指示条，不使用过渡动画。 */
.app-header__nav {
  display: flex;
  align-items: stretch;
  align-self: stretch;
  gap: 24px;
  min-width: 0;
}

.app-header__nav-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 0 2px;
  color: var(--text-secondary);
  font-size: 13.5px;
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
}

.app-header__nav-item:hover {
  color: var(--text-primary);
}

.app-header__nav-item--active {
  color: var(--accent-blue);
  font-weight: 600;
}

.app-header__nav-item--active::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  border-radius: var(--radius-full);
  background: var(--accent-blue);
}

/* ── 账号区 ── */
.app-header__user {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.app-header__user-btn {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 5px 10px 5px 5px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-family: inherit;
  cursor: pointer;
}

.app-header__user-btn:hover {
  border-color: var(--border-strong);
}

.app-header__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-full);
  background: var(--accent-blue);
  color: var(--text-on-accent);
  overflow: hidden;
  flex-shrink: 0;
}

.app-header__avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.app-header__avatar-icon {
  font-size: 16px;
}

.app-header__user-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
  max-width: 160px;
}

.app-header__username {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.app-header__role {
  font-size: 10.5px;
  color: var(--text-tertiary);
  letter-spacing: 0.02em;
}

.app-header__caret {
  font-size: 13px;
  color: var(--text-tertiary);
}

.app-header__menu-note {
  font-size: 12px;
  color: var(--text-tertiary);
}

.app-header__login {
  padding: 7px 16px;
  border-radius: var(--radius-full);
  background: var(--accent-blue);
  color: var(--text-on-accent);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

/* ── 主内容区：全站唯一滚动容器 ── */
.app-main {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 70% 版心：页脚与页面内容同轴。
   横向内边距**不在这里给** —— `.page` 自带 24px 内边距（规约 §2.6），
   这里再给一次会与顶栏内层错开 24px（`.app-header__inner` 的 padding 24px 只算一次）。 */
.app-frame {
  display: flex;
  flex-direction: column;
  width: 70%;
  min-height: 100%;
  margin: 0 auto;
}

/* 页面根容器：高度由内容决定（`flex: 1 0 auto` 保证短页也撑满、长页把页脚顶下去）。
   滚动归 `.app-main`，页面自身不再设 overflow 与固定高度。 */
.app-frame :deep(.page) {
  flex: 1 0 auto;
}

/* 窄屏降级：70% 在中小屏会挤到不可用，逐档放宽（桌面仍为 70%） */
@media (max-width: 1180px) {
  .app-header__inner,
  .app-frame {
    width: 86%;
  }
}

@media (max-width: 900px) {
  .app-header__inner,
  .app-frame {
    width: 100%;
  }

  .app-header__inner {
    gap: 16px;
  }

  .app-header__badge {
    display: none;
  }

  .app-header__nav {
    gap: 16px;
  }

  .app-header__user-meta {
    display: none;
  }
}
</style>
