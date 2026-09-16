import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ensureSonicSession } from '@/api/sonicHttp'
import {
  isLlmEvalApiPack,
  isModuleEnabled,
  LLM_EVAL_DISABLED_PORTAL_MESSAGE
} from '@/config/packProfile'
import fullEditionModuleRoutes from './fullEditionModuleRoutes.js'

const routes = [
  // ========== 顶层入口 ==========
  { path: '/', name: 'Root', component: () => import('@/views/RootRedirect.vue'), meta: { requiresAuth: false } },
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { requiresAuth: false } },
  { path: '/register', name: 'Register', component: () => import('@/views/Register.vue'), meta: { requiresAuth: false } },
  { path: '/reports/detail/:id', name: 'TestReportDetail', component: () => import('@/views/reports/TestReportDetail.vue'), meta: { requiresAuth: false } },

  // ========== 门户模块 (PortalLayout - 无业务侧边栏) ==========
  {
    path: '/dashboard',
    component: () => import('@/layouts/PortalLayout.vue'),
    meta: { requiresAuth: true, layout: 'portal' },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') }
    ]
  },

  // 系统设置
  {
    path: '/settings',
    component: () => import('@/layouts/PortalLayout.vue'),
    meta: { requiresAuth: true, layout: 'portal' },
    children: [
      { path: '', name: 'SystemSettings', component: () => import('@/views/settings/SystemSettings.vue'), meta: { title: '全局系统配置' } },
      { path: 'channel-config', name: 'ChannelConfig', component: () => import('@/views/settings/ChannelConfig.vue'), meta: { title: '消息通道配置' } },
      { path: 'email-config', name: 'EmailConfig', component: () => import('@/views/notifications/EmailConfigList.vue'), meta: { title: '邮件服务配置' } },
      { path: 'general-params', name: 'GeneralSystemParams', component: () => import('@/views/settings/GeneralSystemParams.vue'), meta: { title: '通用系统参数' } },
      { path: 'menu-config', name: 'MenuConfig', component: () => import('@/views/settings/MenuConfig.vue'), meta: { title: '工作区菜单配置' } },
      { path: 'notification-channels', redirect: '/settings/channel-config' }
    ]
  },

  // 个人资料
  {
    path: '/profile',
    component: () => import('@/layouts/PortalLayout.vue'),
    meta: { requiresAuth: true, layout: 'portal' },
    children: [
      { path: '', name: 'Profile', component: () => import('@/views/Profile.vue') }
    ]
  },

  // AI配置管理
  {
    path: '/ai-config',
    component: () => import('@/layouts/PortalLayout.vue'),
    meta: { requiresAuth: true, layout: 'portal' },
    children: [
      { path: '', name: 'AIConfig', component: () => import('@/views/ai_config/AIConfig.vue'), meta: { title: 'AI 实验室配置' } },
      { path: 'llm', name: 'LLMConfig', component: () => import('@/views/ai_config/LLMConfig.vue'), meta: { title: 'LLM模型配置' } },
      { path: 'rag', name: 'RAGConfig', component: () => import('@/views/ai_config/RAGConfig.vue'), meta: { title: 'RAG向量数据库配置' } },
      { path: 'mcp', name: 'MCPConfig', component: () => import('@/views/ai_config/MCPConfig.vue'), meta: { title: 'MCP配置' } }
    ]
  },

  // LLM设置 (保持向后兼容)
  {
    path: '/llm-settings',
    redirect: '/ai-config/llm'
  },

  // ========== L2 业务线项目列表 (PortalLayout - 无侧边栏，领域门户) ==========
  {
    path: '/api-testing/projects',
    component: () => import('@/layouts/PortalLayout.vue'),
    meta: { requiresAuth: true, layout: 'portal', title: 'API 测试项目列表' },
    children: [
      { path: '', name: 'APIProjectList', component: () => import('@/views/api-testing/APIProjectList.vue') }
    ]
  },

  // ========== 工作区模块 (WorkspaceLayout / MainLayout - 有动态侧边栏) ==========

  // 项目管理
  {
    path: '/project',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true, layout: 'workspace', module: 'project', title: '项目管理' },
    children: [
      { path: '', redirect: '/project/project-list' },
      { path: 'project-list', name: 'ProjectList', component: () => import('@/views/project/ProjectList.vue') },
      { path: 'project-detail/:id', name: 'ProjectDetail', component: () => import('@/views/project/ProjectDetail.vue') },
      { path: 'knowledge-base', name: 'KnowledgeBase', component: () => import('@/views/project/KnowledgeBase.vue') },
      { path: 'environments', name: 'ProjectEnvironments', component: () => import('@/views/project/ProjectEnvironments.vue'), meta: { title: '环境管理' } },
      { path: 'scheduled-tasks', name: 'ProjectScheduledTasks', component: () => import('@/views/scheduledTasks/ScheduledTasksPage.vue'), meta: { title: '定时任务' } },
      { path: 'notification-receivers', name: 'ProjectNotificationReceivers', component: () => import('@/views/project/NotificationReceivers.vue'), meta: { title: '通知接收管理' } }
    ]
  },

  // API测试管理
  {
    path: '/api-testing',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true, layout: 'workspace', module: 'api', title: 'API 测试' },
    children: [
      { path: '', redirect: '/api-testing/function-navigation' },
      { path: 'function-navigation', name: 'FunctionNavigation', component: () => import('@/views/api-testing/FunctionNavigation.vue') },
      { path: 'api-specs', name: 'APITesting', component: () => import('@/views/api-testing/ApiSpecManage.vue') },
      { path: 'specs/:id', name: 'APISpecDetail', component: () => import('@/views/api-testing/APISpecDetail.vue') },
      { path: 'scenario-generator', name: 'ScenarioGenerator', component: () => import('@/views/api-testing/ScenarioGenerator.vue'), meta: { title: '智能场景生成器' } },
      { path: 'test-cases', redirect: '/api-testing/test-cases/endpoint' },
      { path: 'test-cases/endpoint', name: 'EndpointTestCases', component: () => import('@/views/api-testing/EndpointTestCases.vue'), meta: { title: '端点测试用例' } },
      { path: 'test-cases/scenario', name: 'ScenarioTestCases', component: () => import('@/views/api-testing/ScenarioOrchestratorPage.vue'), meta: { title: '场景测试用例' } },
      { path: 'test-suites', name: 'ApiTestSuites', component: () => import('@/views/api-testing/TestSuites.vue'), meta: { title: '测试套件管理' } },
      { path: 'test-executions', name: 'ApiTestExecutions', component: () => import('@/views/api-testing/TestExecutions.vue'), meta: { title: '测试执行记录' } },
      { path: 'scheduled-tasks', name: 'ApiScheduledTasks', component: () => import('@/views/scheduledTasks/ScheduledTasksPage.vue'), meta: { title: '定时任务' } },
      { path: 'environments', name: 'ApiEnvironments', component: () => import('@/views/project/ProjectEnvironments.vue'), meta: { title: '环境管理' } },
      { path: 'notification-receivers', name: 'ApiNotificationReceivers', component: () => import('@/views/project/NotificationReceivers.vue'), meta: { title: '通知接收管理' } },
      { path: 'knowledge-base', name: 'ApiKnowledgeBase', component: () => import('@/views/project/KnowledgeBase.vue'), meta: { title: '知识库管理' } }
    ]
  }
]

const allRoutes = [...routes, ...fullEditionModuleRoutes]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes: allRoutes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  if (to.path === '/') {
    return next()
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return next('/login')
  }

  if (to.path === '/login' && authStore.isAuthenticated) {
    return next('/dashboard')
  }

  if (isLlmEvalApiPack()) {
    const blockedPrefixes = [
      { prefix: '/web-testing', module: 'web' },
      { prefix: '/app-testing', module: 'app' },
      { prefix: '/perf-testing', module: 'perf' }
    ]
    for (const { prefix, module } of blockedPrefixes) {
      if (to.path.startsWith(prefix) && !isModuleEnabled(module)) {
        ElMessage.warning(LLM_EVAL_DISABLED_PORTAL_MESSAGE)
        return next('/dashboard')
      }
    }
  }

  // 仅在进入 App 自动化域时自动登录 Sonic（避免全站无谓鉴权）
  const enteringAppTesting = to.path.startsWith('/app-testing') && !from.path.startsWith('/app-testing')
  if (enteringAppTesting) {
    await ensureSonicSession({ silent: true })
  }

  next()
})

export default router
