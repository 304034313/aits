import api from './index'

/** 性能压测场景列表（DRF 分页：count / results） */
export const getPerformanceScenarios = (params = {}) =>
  api.get('/performance/scenarios/', { params }).then((r) => r.data)

/** 单个场景详情（含最近执行的聚合指标等） */
export const getPerformanceScenario = (id) =>
  api.get(`/performance/scenarios/${id}/`).then((r) => r.data)

export const createPerformanceScenario = (data) =>
  api.post('/performance/scenarios/', data).then((r) => r.data)

export const updatePerformanceScenario = (id, data) =>
  api.patch(`/performance/scenarios/${id}/`, data).then((r) => r.data)

export const deletePerformanceScenario = (id) =>
  api.delete(`/performance/scenarios/${id}/`).then((r) => r.data)

/** 启动压测：POST .../scenarios/:id/start-execution/ */
export const startPerformanceExecution = (scenarioId, config, options = {}) =>
  api
    .post(`/performance/scenarios/${scenarioId}/start-execution/`, {
      config,
      is_notify: Boolean(options.is_notify),
      notify_on: options.notify_on === 'all' ? 'all' : 'success',
      frontend_base_url: options.frontend_base_url || '',
      notification_receiver_id:
        options.notification_receiver_id == null ? null : Number(options.notification_receiver_id)
    })
    .then((r) => r.data)

/** 拉取并清空 Redis 中的压测完成事件（当前用户） */
export const getPerformanceNotifications = () =>
  api.get('/performance/notifications/').then((r) => r.data)

/** 压测执行记录列表（DRF 分页） */
export const getPerformanceExecutions = (params = {}) =>
  api.get('/performance/executions/', { params }).then((r) => r.data)

/** 单次执行详情（报告详情页） */
export const getPerformanceExecution = (id) =>
  api.get(`/performance/executions/${id}/`).then((r) => r.data)

/** 发压配置模板列表（后端可能返回数组、DRF results、或 { data: { results } } 等） */
export function getLoadConfigurations(params = {}) {
  return api.get('/performance/load-configurations/', { params }).then((r) => r.data)
}

export const createLoadConfiguration = (data) =>
  api.post('/performance/load-configurations/', data).then((r) => r.data)

export const updateLoadConfiguration = (id, data) =>
  api.patch(`/performance/load-configurations/${id}/`, data).then((r) => r.data)

export const deleteLoadConfiguration = (id) =>
  api.delete(`/performance/load-configurations/${id}/`).then((r) => r.data)

/** 压测监控大盘：Worker + Celery active + DB 活跃执行 */
export const getPerformanceMonitorStatus = (params = {}) =>
  api.get('/performance/monitor/status/', { params }).then((r) => r.data)

/** 手动刷新 Prometheus file_sd 的 windows_exporter 目标 IP */
export const refreshPerformancePromSd = () =>
  api.post('/performance/monitor/refresh-prom-sd/').then((r) => r.data)

/** 获取 Grafana AI 告警默认接收者配置 */
export const getGrafanaNotifyTarget = () =>
  api.get('/performance/monitor/grafana-notify-target/').then((r) => r.data)

/** 更新 Grafana AI 告警默认接收者配置 */
export const setGrafanaNotifyTarget = (data = {}) =>
  api.post('/performance/monitor/grafana-notify-target/', data).then((r) => r.data)

/** 获取项目级第三方集成配置 */
export const getThirdPartyConfig = (projectId) =>
  api.get('/projects/third-party-config/', { params: { project_id: projectId } }).then((r) => r.data)

/** 保存项目级第三方集成配置 */
export const saveThirdPartyConfig = (data = {}) =>
  api.post('/projects/third-party-config/', data).then((r) => r.data)

/** 强行终止 pending/running 的执行 */
export const terminatePerformanceExecution = (id) =>
  api.post(`/performance/monitor/executions/${id}/terminate/`).then((r) => r.data)

/** 清理 DB 中无 Celery 实况的 running/pending 压测记录（僵尸） */
export const cleanPerformanceZombieTasks = (data = {}) =>
  api.post('/performance/monitor/clean-zombies/', data).then((r) => r.data)

/** AI 诊断记录列表 */
export const getAiDiagnosisRecords = (params = {}) =>
  api.get('/performance/ai-diagnosis-records/', { params }).then((r) => r.data)

/** AI 诊断记录详情 */
export const getAiDiagnosisRecord = (id) =>
  api.get(`/performance/ai-diagnosis-records/${id}/`).then((r) => r.data)

/** 更新 AI 诊断记录状态（pending/resolved/ignored） */
export const updateAiDiagnosisRecord = (id, data) =>
  api.patch(`/performance/ai-diagnosis-records/${id}/`, data).then((r) => r.data)
