import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMenuConfig } from '@/api/settings'

/**
 * 默认菜单配置 — 从 MainLayout.vue 迁移而来，作为后端无配置时的降级方案。
 * 注意：icon 字段仅用于 perf 模块渲染，JSON 序列化时会被忽略，
 *       前端渲染时通过 ICON_MAP 重新映射。
 */
export const DEFAULT_MENU_CONFIG = {
  project: {
    title: '项目管理',
    items: [
      { path: '/project/project-list', label: '项目列表', visible: true },
      { path: '/project/environments', label: '环境管理', visible: true },
      { path: '/project/knowledge-base', label: '知识库管理', visible: true },
      { path: '/project/scheduled-tasks', label: '定时任务', visible: true },
      { path: '/project/notification-receivers', label: '通知接收管理', visible: true }
    ]
  },
  api: {
    title: 'API 测试',
    items: [
      { path: '/api-testing/function-navigation', label: 'API功能导航', visible: true },
      { path: '/api-testing/api-specs', label: 'API规范管理', visible: true },
      { path: '/api-testing/scenario-generator', label: 'AI场景智能体', visible: true },
      {
        path: '/api-testing/test-cases',
        label: '测试用例管理',
        visible: true,
        children: [
          { path: '/api-testing/test-cases/endpoint', label: '端点测试用例', visible: true },
          { path: '/api-testing/test-cases/scenario', label: '场景测试用例', visible: true }
        ]
      },
      { path: '/api-testing/test-suites', label: '测试套件管理', visible: true },
      { path: '/api-testing/test-executions', label: '测试执行记录', visible: true },
      { path: '/api-testing/knowledge-base', label: '知识库管理', visible: true },
      { path: '/api-testing/scheduled-tasks', label: '定时任务', visible: true },
      { path: '/api-testing/environments', label: '环境管理', visible: true },
      { path: '/api-testing/notification-receivers', label: '通知接收管理', visible: true }
    ]
  },
  web: {
    title: 'Web 测试',
    items: [
      { path: '/web-testing/test-case-generator', label: '测试用例生成智能体', visible: true },
      { path: '/web-testing/webui-auto-test', label: 'AI 脚本实验室', visible: true },
      { path: '/web-testing/test-cases', label: '测试用例管理', visible: true },
      { path: '/web-testing/test-suites', label: '测试套件管理', visible: true },
      { path: '/web-testing/test-executions', label: '测试执行记录', visible: true },
      { path: '/web-testing/knowledge-base', label: '知识库管理', visible: true },
      { path: '/web-testing/scheduled-tasks', label: '定时任务', visible: true },
      { path: '/web-testing/environments', label: '环境管理', visible: true },
      { path: '/web-testing/page-objects', label: '元素库管理', visible: true },
      { path: '/web-testing/notification-receivers', label: '通知接收管理', visible: true }
    ]
  },
  app: {
    title: 'App 自动化测试',
    items: [
      { path: '/app-testing/device-management', label: '设备管理', visible: true },
      { path: '/app-testing/page-element-management', label: '页面元素管理', visible: true },
      { path: '/app-testing/test-cases', label: '测试用例管理', visible: true },
      { path: '/app-testing/test-suites', label: '测试套件管理', visible: true },
      { path: '/app-testing/test-runs', label: '测试执行记录', visible: true },
      { path: '/app-testing/scheduled-tasks', label: '定时任务', visible: true },
      { path: '/app-testing/environments', label: 'Agent 管理', visible: true },
      { path: '/app-testing/notification-receivers', label: '通知接收管理', visible: true }
    ]
  },
  perf: {
    title: '性能专项测试',
    items: [
      {
        path: '/perf-testing/performance',
        label: '性能测试',
        iconName: 'TrendCharts',
        visible: true,
        children: [
          { path: '/perf-testing/dashboard', label: '性能大盘', iconName: 'TrendCharts', visible: true },
          { path: '/perf-testing/scenarios', label: '压测场景', iconName: 'Operation', visible: true },
          { path: '/perf-testing/config', label: '发压配置', iconName: 'Setting', visible: true },
          { path: '/perf-testing/monitor', label: '任务监控', iconName: 'DataAnalysis', visible: true },
          { path: '/perf-testing/reports', label: '压测记录', iconName: 'Document', visible: true },
          { path: '/perf-testing/ai-diagnosis', label: 'AI 诊断记录', iconName: 'TrendCharts', visible: true }
        ]
      },
      { path: '/perf-testing/notification-receivers', label: '通知接收管理', iconName: 'Bell', visible: true },
      { path: '/perf-testing/grafana-config', label: '监控集成配置', iconName: 'Setting', visible: true }
    ]
  }
}

function filterVisible(items) {
  if (!items) return []
  return items
    .filter(item => item.visible !== false)
    .map(item => {
      if (item.children) {
        return { ...item, children: filterVisible(item.children) }
      }
      return item
    })
}

export const useMenuStore = defineStore('menu', () => {
  const configMap = ref({})
  const loaded = ref(false)

  async function fetchMenuConfig() {
    try {
      const res = await getMenuConfig()
      const data = res.data?.data
      if (data && typeof data === 'object') {
        configMap.value = data
      }
    } catch {
      // 接口不可用时静默降级到默认配置
    } finally {
      loaded.value = true
    }
  }

  function getMenuItems(module) {
    const remote = configMap.value[module]
    if (remote && Array.isArray(remote) && remote.length > 0) {
      return filterVisible(remote)
    }
    const defaults = DEFAULT_MENU_CONFIG[module]
    return defaults ? filterVisible(defaults.items) : []
  }

  function findMenuLabelByPath(path) {
    for (const mod of Object.keys(DEFAULT_MENU_CONFIG)) {
      const items = getMenuItems(mod)
      for (const item of items) {
        if (item.path === path) return item.label
        if (item.children) {
          const child = item.children.find(c => c.path === path)
          if (child) return child.label
        }
      }
    }
    return null
  }

  return { configMap, loaded, fetchMenuConfig, getMenuItems, findMenuLabelByPath }
})
