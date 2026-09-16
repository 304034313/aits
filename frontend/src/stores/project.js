import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { usersApi } from '@/api/users'
import { getProjects } from '@/api/projects'

export const useProjectStore = defineStore('project', () => {
  // 状态
  const currentProject = ref(null)
  const projects = ref([])
  const loading = ref(false)
  const workingDeviceByProject = ref({})

  // 计算属性
  const hasCurrentProject = computed(() => !!currentProject.value)
  const currentProjectId = computed(() => currentProject.value?.id || null)
  /** Sonic 平台项目 ID（App 测试直连 Sonic API）；未配置时为 null */
  const currentSonicProjectId = computed(() => {
    const raw = currentProject.value?.sonic_project_id
    if (raw == null || raw === '') return null
    const n = Number(raw)
    return Number.isFinite(n) && n > 0 ? n : null
  })
  const currentWorkingDevice = computed(() => {
    const pid = currentProjectId.value
    if (!pid) return null
    return workingDeviceByProject.value[String(pid)] || null
  })


  // 加载项目列表
  const loadProjects = async () => {
    const response = await getProjects()
    projects.value = response.success && response.data ? (response.data.items || []) : []
  }

  // 从用户偏好设置加载当前项目
  const loadUserPreferences = async () => {
    loading.value = true
    
    const response = await usersApi.getPreferences()
    const { selectedProject } = response.data

    // 设置当前项目
    if (selectedProject && selectedProject.id) {
      currentProject.value = selectedProject
    } else {
      // 如果没有保存的项目，加载项目列表并设置第一个项目
      await loadProjects()
      if (projects.value.length > 0) {
        currentProject.value = projects.value[0]
      }
    }
    
    loading.value = false
  }

  // 设置当前项目
  const setCurrentProject = async (project) => {
    loading.value = true
    currentProject.value = project
    await usersApi.setSelectedProject(project)
    loading.value = false
  }

  // 设置当前项目（本地生效，不写入后端偏好）
  // 用于 App 测试项目直连 Sonic 的场景，避免在“App 项目创建/选择”时走 AITS 平台后端
  const setCurrentProjectLocal = (project) => {
    loading.value = true
    currentProject.value = project
    loading.value = false
  }

  // 根据ID设置当前项目
  const setCurrentProjectById = async (projectId) => {
    if (!projectId) return await clearCurrentProject()
    
    if (projects.value.length === 0) await loadProjects()
    const project = projects.value.find(p => p.id === projectId)
    if (project) {
      await setCurrentProject(project)
    }
  }

  // 清除当前项目
  const clearCurrentProject = async () => {
    loading.value = true
    const pid = currentProject.value?.id
    if (pid) {
      const next = { ...workingDeviceByProject.value }
      delete next[String(pid)]
      workingDeviceByProject.value = next
    }
    currentProject.value = null
    await usersApi.clearSelectedProject()
    loading.value = false
  }

  const setCurrentWorkingDevice = (device) => {
    const pid = currentProjectId.value
    if (!pid || !device?.deviceId) return
    const prev = workingDeviceByProject.value[String(pid)] || {}
    workingDeviceByProject.value = {
      ...workingDeviceByProject.value,
      [String(pid)]: {
        deviceId: device.deviceId,
        name: device.name ?? prev.name ?? '',
        chiName: device.chiName ?? prev.chiName ?? '',
        platform: device.platform ?? prev.platform ?? '',
        model: device.model ?? prev.model ?? '',
        status: device.status ?? prev.status ?? '',
        rawStatus: device.rawStatus ?? prev.rawStatus ?? '',
        udId: device.udId ?? prev.udId ?? '',
        isOccupied: device.isOccupied ?? prev.isOccupied ?? false
      }
    }
  }

  const clearCurrentWorkingDevice = () => {
    const pid = currentProjectId.value
    if (!pid) return
    const next = { ...workingDeviceByProject.value }
    delete next[String(pid)]
    workingDeviceByProject.value = next
  }



  // 初始化用户偏好设置
  const initializeUserPreferences = async () => {
    // 如果已经有当前项目，不需要重新初始化
    if (currentProject.value) {
      return
    }

    await loadUserPreferences()
  }

  // 重置store状态
  const reset = () => {
    currentProject.value = null
    projects.value = []
    loading.value = false
    workingDeviceByProject.value = {}
  }

  return {
    // 状态（workingDeviceByProject 必须导出，setup store 才会纳入 $state，持久化插件才能写入 localStorage）
    currentProject,
    projects,
    loading,
    workingDeviceByProject,

    // 计算属性
    hasCurrentProject,
    currentProjectId,
    currentSonicProjectId,
    currentWorkingDevice,

    // 方法
    loadProjects,
    loadUserPreferences,
    setCurrentProject,
    setCurrentProjectLocal,
    setCurrentProjectById,
    clearCurrentProject,
    setCurrentWorkingDevice,
    clearCurrentWorkingDevice,
    initializeUserPreferences,
    reset
  }
}, {
  // 持久化配置
  persist: {
    key: 'project-store',
    storage: localStorage,
    paths: ['currentProject', 'workingDeviceByProject']
  }
})