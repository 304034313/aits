import api from './index'

const basePath = (projectId) => `/projects/${projectId}/app-testing/scheduled-tasks`

export const getAppScheduledTasks = async (projectId, params = {}) => {
  const response = await api.get(`${basePath(projectId)}/tasks/`, { params })
  return response.data
}

export const getAppScheduledTask = async (projectId, id) => {
  const response = await api.get(`${basePath(projectId)}/tasks/${id}/`)
  return response.data
}

export const createAppScheduledTask = async (projectId, data) => {
  const response = await api.post(`${basePath(projectId)}/tasks/`, data)
  return response.data
}

export const updateAppScheduledTask = async (projectId, id, data) => {
  const response = await api.put(`${basePath(projectId)}/tasks/${id}/`, data)
  return response.data
}

export const deleteAppScheduledTask = async (projectId, id) => {
  const response = await api.delete(`${basePath(projectId)}/tasks/${id}/`)
  return response.data
}

export const runAppScheduledTask = async (projectId, id) => {
  const response = await api.post(`${basePath(projectId)}/tasks/${id}/run/`)
  return response.data
}

export const getAppExecutionLogs = async (projectId, params = {}) => {
  const response = await api.get(`${basePath(projectId)}/execution-logs/`, { params })
  return response.data
}

export const getAppExecutionLog = async (projectId, id) => {
  const response = await api.get(`${basePath(projectId)}/execution-logs/${id}/`)
  return response.data
}

export const deleteAppExecutionLog = async (projectId, id) => {
  const response = await api.delete(`${basePath(projectId)}/execution-logs/${id}/`)
  return response.data
}

export const getAppTaskExecutionLogs = async (projectId, taskId, params = {}) => {
  const response = await api.get(`${basePath(projectId)}/tasks/${taskId}/execution-logs/`, { params })
  return response.data
}

export const getAppSuiteChoices = async (projectId) => {
  const response = await api.get(`${basePath(projectId)}/suite-choices/`)
  return response.data
}

export const getAppScheduledTaskStatistics = async (projectId) => {
  const response = await api.get(`${basePath(projectId)}/statistics/`)
  return response.data
}
