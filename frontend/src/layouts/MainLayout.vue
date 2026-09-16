<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="sidebar">
      <div class="sidebar-header">
        <AITSBrand size="small" />
      </div>

      <!-- 工作区头部：返回链接 + 项目身份区（项目名 + 模块名） -->
      <div class="workspace-header">
        <a class="back-link" @click.prevent="goBackToProjectList">
          <el-icon><Back /></el-icon>
          <span>返回列表</span>
        </a>
        <div class="identity-strip">
          <div v-if="currentProject" class="project-row">
            <el-icon class="project-icon"><FolderOpened /></el-icon>
            <span class="project-name">{{ currentProject.name }}</span>
          </div>
          <div class="module-row">{{ currentMenuName }}</div>
        </div>
      </div>

      <!-- 动态上下文菜单：仅渲染当前模块的子菜单 -->
      <el-menu
        v-if="dynamicMenus.length > 0"
        :default-active="activeMenuIndex"
        class="sidebar-menu"
        router
        background-color="transparent"
        text-color="var(--layout-sidebar-text)"
        active-text-color="var(--layout-sidebar-active)"
        @select="handleMenuSelect"
      >
        <template v-for="item in dynamicMenus" :key="item.path">
          <el-sub-menu v-if="item.children" :index="item.path">
            <template #title>
              <span class="submenu-title">
                <el-icon v-if="item.icon || item.iconName" class="menu-title-icon"><component :is="resolveIcon(item)" /></el-icon>
                {{ item.label }}
              </span>
            </template>
            <el-menu-item
              v-for="child in item.children"
              :key="child.path"
              :index="child.path"
            >
              <el-icon class="menu-title-icon"><component :is="resolveIcon(child)" /></el-icon>
              {{ child.label }}
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-else :index="item.path">
            <el-icon class="menu-title-icon"><component :is="resolveIcon(item)" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <!-- 右侧内容区 -->
    <el-container class="main-wrapper">
      <!-- 顶部导航 -->
      <el-header class="header">
        <div class="header-right">
          <el-button-group class="theme-toggle" size="small">
            <el-tooltip content="亮色" placement="bottom">
              <el-button :type="appStore.themeMode === 'light' ? 'primary' : 'default'" @click="appStore.setThemeMode('light')">
                <el-icon><Sunny /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="深色极客" placement="bottom">
              <el-button :type="appStore.themeMode === 'dark' ? 'primary' : 'default'" @click="appStore.setThemeMode('dark')">
                <el-icon><Moon /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="跟随系统" placement="bottom">
              <el-button :type="appStore.themeMode === 'auto' ? 'primary' : 'default'" @click="appStore.setThemeMode('auto')">
                <el-icon><Monitor /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="30" :src="authStore.user?.avatar">
                {{ authStore.user?.username?.charAt(0)?.toUpperCase() }}
              </el-avatar>
              <span class="username">{{ authStore.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人资料</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 多标签页栏 -->
      <div class="tab-bar">
        <div class="tab-list" ref="tabListRef">
          <div
            v-for="tab in tabStore.tabs"
            :key="tab.path"
            class="tab-item"
            :class="{ 'tab-item--active': tabStore.activeTab === tab.path }"
            @click="switchTab(tab.path)"
            @contextmenu.prevent="openContextMenu($event, tab)"
          >
            <span class="tab-title">{{ tab.title }}</span>
            <!-- 刷新图标：仅在当前激活 Tab 上显示 -->
            <el-icon
              v-if="tabStore.activeTab === tab.path"
              class="tab-refresh"
              title="刷新当前页面"
              @click.stop="reload(route.fullPath)"
            >
              <RefreshRight />
            </el-icon>
            <el-icon
              v-if="tab.closable"
              class="tab-close"
              @click.stop="closeTab(tab.path)"
            >
              <Close />
            </el-icon>
          </div>
        </div>
      </div>

      <!-- 右键菜单 -->
      <div
        v-if="contextMenu.visible"
        class="context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div class="context-menu-item" @click="handleContextMenuAction('refresh')">
          <el-icon><RefreshRight /></el-icon> 刷新当前
        </div>
        <div class="context-menu-divider" />
        <div class="context-menu-item" @click="handleContextMenuAction('close')">
          <el-icon><Close /></el-icon> 关闭当前
        </div>
        <div class="context-menu-item" @click="handleContextMenuAction('closeOthers')">
          <el-icon><Remove /></el-icon> 关闭其他
        </div>
        <div class="context-menu-item" @click="handleContextMenuAction('closeAll')">
          <el-icon><CircleClose /></el-icon> 关闭所有
        </div>
      </div>

      <!-- 主内容 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component, route: currentRoute }">
          <keep-alive :max="15">
            <component
              :is="Component"
              :key="currentRoute.fullPath + (refreshKeyMap[currentRoute.fullPath] || 0)"
            />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick, provide, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElButton, ElMessageBox, ElNotification } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { useTabStore, getRouteTitle } from '@/stores/tabs'
import {
  ArrowDown, Back,
  RefreshRight, Close, Remove, CircleClose,
  Sunny, Moon, Monitor, FolderOpened, TrendCharts, Menu, Setting, DataAnalysis, Operation, Document, Bell
} from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { useMenuStore } from '@/stores/menu'
import { usePerfRunNotifySnapshotStore } from '@/stores/perfRunNotifySnapshot'
import { getPerformanceNotifications, getPerformanceScenarios } from '@/api/performance'
import AITSBrand from '@/components/AITSBrand.vue'


const ICON_MAP = { TrendCharts, Operation, Setting, DataAnalysis, Document, Bell, Menu }
function resolveIcon(item) {
  if (item.icon) return item.icon
  if (item.iconName) return ICON_MAP[item.iconName] || Menu
  return Menu


}

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const projectStore = useProjectStore()
const tabStore = useTabStore()
const appStore = useAppStore()
const menuStore = useMenuStore()

const tabListRef = ref(null)

// -------- 局部刷新机制（动态 Key 击穿 keep-alive 缓存）--------
// 每个路由 fullPath 对应一个自增计数器；计数变化 → key 变化 → keep-alive 视为新实例 → onMounted 重新执行
const refreshKeyMap = ref({})

const reload = (path) => {
  const key = path || route.fullPath
  refreshKeyMap.value[key] = (refreshKeyMap.value[key] || 0) + 1
}
// 向所有子组件提供 reload 方法，子组件可通过 inject('reload') 主动触发刷新
provide('reload', reload)

// 右键菜单状态
const contextMenu = ref({ visible: false, x: 0, y: 0, tab: null })

// -------- 路由监听：自动添加 Tab --------
watch(() => route.path, (path) => {
  if (!path || path === '/') return
  const title = getRouteTitle(path, route.meta)
  tabStore.addTab(path, title)
  nextTick(() => scrollActiveTabIntoView())
}, { immediate: true })

// -------- Tab 操作 --------
const switchTab = (path) => {
  tabStore.setActiveTab(path)
  router.push(path)
}

const closeTab = (path) => {
  tabStore.removeTab(path, router)
}

const openContextMenu = (e, tab) => {
  contextMenu.value = { visible: true, x: e.clientX, y: e.clientY, tab }
}

const handleContextMenuAction = (action) => {
  const { tab } = contextMenu.value
  contextMenu.value.visible = false
  if (!tab) return
  switch (action) {
    case 'refresh':
      if (tab.path === tabStore.activeTab) {
        reload(route.fullPath)
      } else {
        switchTab(tab.path)
        nextTick(() => reload(tab.path))
      }
      break
    case 'close':
      if (tab.closable) closeTab(tab.path)
      break
    case 'closeOthers':
      tabStore.closeOtherTabs(tab.path, router)
      break
    case 'closeAll':
      tabStore.closeAllTabs(router)
      break
  }
}

// 左侧菜单 select 事件：点击当前已激活路由时触发刷新
const handleMenuSelect = (index) => {
  if (index === route.path) reload(route.fullPath)
}

// 点击其他区域关闭右键菜单
const hideContextMenu = () => { contextMenu.value.visible = false }
onMounted(() => document.addEventListener('click', hideContextMenu))

/** 压测完成：Redis 事件 + 场景列表差分，全局轮询（切换菜单后仍生效） */
const PERF_WATCH_INTERVAL_MS = 300000 // 5 分钟

let perfWatchTimer = null
let isPerfWatching = false
/** 递增：用于丢弃上一轮异步 tick 在 finally 中的重复预约 */
let perfWatchRunId = 0

function clearPerfWatchTimer() {
  isPerfWatching = false
  perfWatchRunId += 1
  if (perfWatchTimer != null) {
    clearTimeout(perfWatchTimer)
    perfWatchTimer = null
  }
}

function normalizePerfWatchListResponse(payload) {
  if (payload == null) return { list: [], total: 0 }
  if (Array.isArray(payload.results)) {
    return { list: payload.results, total: Number(payload.count) || 0 }
  }
  if (payload.success && payload.data) {
    const d = payload.data
    const list = d.items || d.results || (Array.isArray(d) ? d : [])
    const total = d.pagination?.total ?? d.count ?? list.length
    return { list, total: Number(total) || 0 }
  }
  if (Array.isArray(payload)) return { list: payload, total: payload.length }
  return { list: [], total: 0 }
}

function showPerfFinishedNotification(payload) {
  const {
    scenario_name: scenarioName,
    status,
    users,
    avg_response_ms: avgMs,
    execution_id: executionId,
    scenario_id: scenarioId
  } = payload
  const resultText =
    status === 'success' ? '成功' : status === 'failed' ? '失败' : status === 'stopped' ? '已停止' : '已结束'
  const avgStr =
    avgMs != null && avgMs !== '' && !Number.isNaN(Number(avgMs)) ? `${Number(avgMs).toFixed(0)}` : '—'
  const usersStr = users != null && users !== '' ? String(users) : '—'
  const ntype = status === 'failed' ? 'error' : status === 'stopped' ? 'warning' : 'success'

  ElNotification({
    title: '压测任务已完成',
    message: h('div', { class: 'perf-finished-notify' }, [
      h(
        'p',
        { style: 'margin:0 0 10px;line-height:1.55;font-size:13px' },
        `场景 ${scenarioName || '—'} 执行结果：${resultText}，并发数：${usersStr}，平均响应时间：${avgStr} ms。`
      ),
      h(
        ElButton,
        {
          type: 'primary',
          size: 'small',
          onClick: () => {
            if (executionId != null) {
              router.push({ name: 'PerfReportDetail', params: { id: String(executionId) } })
            } else {
              router.push({ name: 'PerfReports' })
            }
          }
        },
        () => '查看报告'
      )
    ]),
    duration: 0,
    position: 'bottom-right',
    type: ntype
  })
}

async function perfGlobalWatchTick(runId) {
  if (!isPerfWatching || runId !== perfWatchRunId) return

  const snapStore = usePerfRunNotifySnapshotStore()
  const prev = snapStore.peekSnapshot()
  const notifiedScenarioIds = new Set()

  try {
    try {
      const raw = await getPerformanceNotifications()
      const events = raw?.events || []
      for (const ev of events) {
        if (ev?.type !== 'perf_execution_finished') continue
        if (ev.scenario_id != null) notifiedScenarioIds.add(ev.scenario_id)
        showPerfFinishedNotification({
          scenario_name: ev.scenario_name,
          status: ev.status,
          users: ev.users,
          avg_response_ms: ev.avg_response_ms,
          execution_id: ev.execution_id,
          scenario_id: ev.scenario_id
        })
      }
    } catch {
      /* 忽略：无 Redis 时走列表差分 */
    }

    const pid = projectStore.currentProjectId
    if (pid) {
      try {
        const raw = await getPerformanceScenarios({ project_id: pid, page_size: 200 })
        const { list } = normalizePerfWatchListResponse(raw)
        for (const row of list) {
          const skipByEvent = notifiedScenarioIds.has(row.id)
          if (skipByEvent) continue
          const was = prev[row.id]
          const cur = row.last_execution_status
          if (was === 'running' && (cur === 'success' || cur === 'failed' || cur === 'stopped')) {
            showPerfFinishedNotification({
              scenario_name: row.name,
              status: cur,
              users: row.last_execution_users,
              avg_response_ms: row.last_execution_avg_response_ms,
              execution_id: row.last_execution_id,
              scenario_id: row.id
            })
          }
        }
        snapStore.applyScenarioRows(list)
      } catch (e) {
        console.warn('[perf-watch] scenarios poll failed', e)
      }
    }
  } finally {
    if (isPerfWatching && runId === perfWatchRunId) {
      perfWatchTimer = setTimeout(() => perfGlobalWatchTick(runId), PERF_WATCH_INTERVAL_MS)
    }
  }
}

const shouldPerfGlobalWatch = computed(() => {
  if (!authStore.isAuthenticated) return false
  if (!projectStore.currentProjectId) return false
  const p = projectStore.currentProject
  if (p?.project_type === 'perf') return true
  if (route.path.startsWith('/perf-testing')) return true
  return false
})

watch(
  shouldPerfGlobalWatch,
  (on) => {
    clearPerfWatchTimer()
    if (on) {
      isPerfWatching = true
      perfWatchRunId += 1
      const runId = perfWatchRunId
      perfGlobalWatchTick(runId)
    }
  },
  { immediate: true }
)

watch(
  () => authStore.isAuthenticated,
  (ok) => {
    if (!ok) clearPerfWatchTimer()
  }
)

onBeforeUnmount(() => {
  document.removeEventListener('click', hideContextMenu)
  clearPerfWatchTimer()
})

// 让激活的 Tab 滚动到可视区域
const scrollActiveTabIntoView = () => {
  if (!tabListRef.value) return
  const activeEl = tabListRef.value.querySelector('.tab-item--active')
  if (activeEl) activeEl.scrollIntoView({ behavior: 'smooth', inline: 'nearest', block: 'nearest' })
}

// -------- 动态菜单：根据当前路由 meta.module 过滤 --------
const currentModule = computed(() => {
  const fromMeta = route.meta?.module
  if (fromMeta) return fromMeta
  // 从路径推断模块（兜底，确保工作区路由总能正确显示菜单）
  if (route.path.startsWith('/api-testing')) return 'api'
  if (route.path.startsWith('/web-testing')) return 'web'
  if (route.path.startsWith('/app-testing')) return 'app'
  if (route.path.startsWith('/perf-testing')) return 'perf'
  if (route.path.startsWith('/project')) return 'project'
  return null
})

const dynamicMenus = computed(() => {
  const module = currentModule.value
  if (!module) return []
  return menuStore.getMenuItems(module)
})

const currentMenuName = computed(() => {
  const label = menuStore.findMenuLabelByPath(activeMenuIndex.value)
  return label || route.meta?.title || '工作区'
})

// -------- 返回项目列表：按业务线跳转到对应 L2 项目列表页 --------
const MODULE_PROJECT_LIST_PATH = {
  api: '/api-testing/projects',
  web: '/web-testing/projects',
  app: '/app-testing/projects',
  perf: '/perf-testing/projects',
  project: '/project/project-list'
}

const backToProjectListPath = computed(() => {
  const module = currentModule.value
  return (module && MODULE_PROJECT_LIST_PATH[module]) || '/dashboard'
})

const goBackToProjectList = () => {
  router.push(backToProjectListPath.value)
}

// -------- 菜单激活状态 --------
const activeMenuIndex = computed(() => {
  const p = route.path
  // 动态路由兜底：详情页高亮对应父级菜单
  if (/^\/api-testing\/specs\/[^/]+/.test(p)) return '/api-testing/api-specs'
  if (/^\/project\/project-detail\/[^/]+/.test(p)) return '/project/project-list'
  // 模块基础路径 -> 默认子页
  if (p === '/api-testing') return '/api-testing/function-navigation'
  if (p === '/web-testing') return '/web-testing/webui-auto-test'
  if (p === '/app-testing') return '/app-testing/page-element-management'
  if (p === '/app-testing/test-cases/new' || /^\/app-testing\/test-cases\/\d+\/edit$/.test(p)) {
    return '/app-testing/test-cases'
  }
  if (p === '/perf-testing') return '/perf-testing/workspace'
  if (p === '/project') return '/project/project-list'
  return p
})

// -------- 其他 --------
const currentProject = computed(() => projectStore.currentProject)

const handleCommand = async (command) => {
  switch (command) {
    case 'profile':
      router.push('/profile')
      break
    case 'logout':
      try {
        await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await authStore.logout()
        tabStore.reset()
        await router.push('/login')
      } catch (e) {
        if (e !== 'cancel') console.error('登出错误:', e)
      }
      break
  }
}

onMounted(async () => {
  menuStore.fetchMenuConfig()
  if (!projectStore.currentProject) {
    await projectStore.initializeUserPreferences()
  }
})
</script>

<style scoped>
.layout-container {
  height: 100vh;
  overflow: hidden;
}

/* 侧边栏 */
.sidebar {
  background-color: var(--layout-sidebar-bg);
  color: var(--layout-sidebar-text);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-header {
  padding: 20px 20px 24px;
  text-align: center;
  border-bottom: 1px solid var(--app-border);
  flex-shrink: 0;
  overflow: visible;
}

/* 工作区头部：返回链接 + 项目身份区 */
.workspace-header {
  padding: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
  text-align: left;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.55);
  text-decoration: none;
  cursor: pointer;
  margin-bottom: 14px;
  transition: color 0.2s;
}

.back-link:hover {
  color: rgba(255, 255, 255, 0.9);
}

.back-link .el-icon {
  font-size: 14px;
}

.identity-strip {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 12px 14px;
}

.project-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--layout-sidebar-text);
  opacity: 0.9;
  margin-bottom: 6px;
}

.project-row .project-icon {
  font-size: 14px;
  flex-shrink: 0;
  color: var(--layout-sidebar-active);
}

.project-row .project-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.module-row {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  line-height: 1.3;
}

.sidebar-menu {
  border: none;
  flex: 1;
  background-color: transparent !important;
}

.submenu-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.menu-title-icon {
  font-size: 16px;
  flex-shrink: 0;
}

/* 右侧主区域 */
.main-wrapper {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* 顶部 Header */
.header {
  background: var(--layout-header-bg);
  border-bottom: 1px solid var(--layout-header-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 52px;
  flex-shrink: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.user-info:hover {
  background-color: var(--layout-hover-bg);
}

.username {
  font-size: 13px;
  color: var(--app-text-primary);
  font-weight: 500;
}

/* 多标签页栏 */
.tab-bar {
  background: var(--layout-tab-bg);
  border-bottom: 1px solid var(--layout-tab-border);
  flex-shrink: 0;
  overflow: hidden;
}

.tab-list {
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  scrollbar-width: none;
  height: 38px;
}

.tab-list::-webkit-scrollbar {
  display: none;
}

.tab-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 14px;
  cursor: pointer;
  font-size: 13px;
  color: var(--app-text-secondary);
  white-space: nowrap;
  border-right: 1px solid var(--layout-tab-border);
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  user-select: none;
  flex-shrink: 0;
  min-width: 80px;
  max-width: 160px;
}

.tab-item:hover {
  color: var(--layout-sidebar-active);
  background-color: var(--layout-hover-bg);
}

.tab-item--active {
  color: var(--layout-sidebar-active);
  background-color: var(--layout-tab-active-bg);
  border-bottom-color: var(--layout-sidebar-active);
  font-weight: 500;
}

.tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.tab-close,
.tab-refresh {
  font-size: 12px;
  flex-shrink: 0;
  color: var(--app-text-muted);
  border-radius: 50%;
  padding: 1px;
  transition: all 0.15s;
}

.tab-close:hover {
  color: #fff;
  background-color: var(--layout-sidebar-active);
}

.tab-refresh:hover {
  color: var(--layout-sidebar-active);
  background-color: var(--layout-tab-active-bg);
}

/* 右键菜单 */
.context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--layout-header-bg);
  border: 1px solid var(--app-border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  min-width: 140px;
  overflow: hidden;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  font-size: 13px;
  color: var(--app-text-primary);
  cursor: pointer;
  transition: background-color 0.15s;
}

.context-menu-item:hover {
  background-color: var(--layout-hover-bg);
  color: var(--layout-sidebar-active);
}

.context-menu-divider {
  height: 1px;
  background-color: var(--app-border-light);
  margin: 3px 0;
}

/* 主内容 */
.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--layout-main-bg);
  padding: 12px;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
