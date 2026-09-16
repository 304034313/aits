/**
 * App 测试：直接调用 Sonic Controller API（projectId 均为 Sonic 的 project id，即 AITS Project.sonic_project_id）
 */
import sonicHttp, { getSonicToken as readSonicTokenFromStore } from './sonicHttp'
import { platformToSonicInt, syncStepsToSonicCase } from './sonicCaseOps'

function noSonicProject() {
  return { success: false, message: '请先在顶部绑定 Sonic 项目', data: null }
}

function normalizeSonicDevice(item) {
  const status = item?.status
  const normalizedStatus = {
    ONLINE: 'online',
    DEBUGGING: 'debugging',
    TESTING: 'testing',
    OFFLINE: 'offline',
    DISCONNECTED: 'disconnected',
    UNAUTHORIZED: 'unauthorized',
    ERROR: 'error'
  }[status] || 'unknown'
  const chiNameRaw = item?.chiName
  const chiName =
    chiNameRaw != null && String(chiNameRaw).trim() ? String(chiNameRaw).trim() : ''
  return {
    deviceId: item?.id,
    udId: item?.udId,
    name: item?.name || item?.nickName || item?.model,
    chiName,
    manufacturer: item?.manufacturer,
    model: item?.model,
    platform: item?.platform,
    version: item?.version,
    status: normalizedStatus,
    rawStatus: status,
    isOccupied: status === 'DEBUGGING' || status === 'TESTING',
    batteryLevel: item?.batteryLevel,
    temperature: item?.tem,
    agentId: item?.agentId,
    agentName: item?.agentName
  }
}

function mapSonicCaseToAits(row, moduleNameMap = {}) {
  const mid = row.moduleId ?? row.module_id ?? 0
  const plat = row.platform
  let platform = 'android'
  if (plat === 2 || plat === '2') platform = 'ios'
  if (plat === 'iOS' || plat === 'IOS') platform = 'ios'
  const modDto = row.modulesDTO || row.modulesDto || null
  const moduleNameFromDto = modDto && typeof modDto.name === 'string' ? modDto.name : ''
  return {
    id: row.id,
    title: row.name,
    name: row.name,
    description: row.des || row.description || '',
    module_id: mid,
    moduleId: mid,
    module_name: moduleNameMap[mid] || row.moduleName || moduleNameFromDto || '',
    platform,
    designer: row.designer,
    editTime: row.editTime,
    version: row.version
  }
}

function flattenStepsTree(items) {
  const out = []
  function walk(arr) {
    for (const s of arr || []) {
      out.push(s)
      if (Array.isArray(s?.childSteps) && s.childSteps.length) walk(s.childSteps)
    }
  }
  walk(items)
  return out
}

/** 与 DeviceRemotePanel 兼容：从本地 SonicToken 读取 */
export async function getSonicToken() {
  const t = readSonicTokenFromStore()
  if (!t) {
    return { success: false, message: '请先绑定 Sonic 账号', data: null }
  }
  return { success: true, data: { token: t }, message: 'ok' }
}

export async function getSonicDevices(sonicProjectId, params = {}) {
  if (!sonicProjectId) {
    return { success: false, message: '未绑定 Sonic 项目', data: { items: [], pagination: {} } }
  }
  try {
    const resp = await sonicHttp.get('/controller/devices/list', { params })
    const data = resp.data || {}
    const content = data.content || []
    const items = content.map(normalizeSonicDevice)
    return {
      success: true,
      data: {
        items,
        pagination: {
          page: (data.number ?? 0) + 1,
          page_size: data.size ?? params.pageSize ?? 12,
          total: data.totalElements ?? 0,
          total_pages: data.totalPages ?? 0
        }
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取设备失败', data: { items: [], pagination: {} } }
  }
}

export async function getSonicDeviceDetail(_sonicProjectId, deviceId) {
  try {
    const resp = await sonicHttp.get('/controller/devices', { params: { id: deviceId } })
    const data = resp.data || {}
    return {
      success: true,
      data: {
        id: data.id ?? deviceId,
        udId: data.udId || data.udid,
        agentId: data.agentId,
        name: data.name || data.nickName || data.model || '',
        platform: data.platform || '',
        version: data.version || '',
        status: data.status,
        raw: data
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取设备详情失败', data: null }
  }
}

export async function getSonicAgentDetail(_sonicProjectId, agentId) {
  try {
    const resp = await sonicHttp.get('/controller/agents', { params: { id: agentId } })
    const data = resp.data || {}
    return {
      success: true,
      data: {
        id: data.id ?? agentId,
        host: data.host || '',
        port: data.port,
        secretKey: data.secretKey || data.secretkey || '',
        systemType: data.systemType,
        raw: data
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取 Agent 失败', data: null }
  }
}

export async function getSonicDeviceFilterOptions(_sonicProjectId) {
  try {
    const resp = await sonicHttp.get('/controller/devices/getFilterOption')
    return { success: true, data: resp.data || {}, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message, data: {} }
  }
}

export async function getSonicDeviceTemperature(_sonicProjectId) {
  try {
    const resp = await sonicHttp.get('/controller/devices/findTemper')
    const value = resp.data
    return { success: true, data: { avgTemperature: value }, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message, data: null }
  }
}

export async function releaseSonicDevice(_sonicProjectId, udId) {
  await sonicHttp.get('/controller/devices/stopDebug', { params: { udId } })
  return { success: true, data: {}, message: '设备释放成功' }
}

export async function getSonicAgents(_sonicProjectId) {
  try {
    const resp = await sonicHttp.get('/controller/agents/list')
    return { success: true, data: { items: resp.data || [] }, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message, data: { items: [] } }
  }
}

/**
 * 新增或更新 Sonic Agent（与 sonic-client-web Agent 中心「保存」一致，对应 PUT /controller/agents/update）
 * @param {Record<string, unknown>} payload AgentsDTO 形状：id 为 0 时表示新增
 */
export async function saveSonicAgent(payload) {
  try {
    await sonicHttp.put('/controller/agents/update', payload)
    return { success: true, data: {}, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message || '保存失败', data: {} }
  }
}

export async function listAppTestApplications(sonicProjectId) {
  if (!sonicProjectId) return { ...noSonicProject(), data: { items: [] } }
  try {
    const resp = await sonicHttp.get('/controller/packages/list', {
      params: { projectId: sonicProjectId, page: 1, pageSize: 500 }
    })
    const page = resp.data || {}
    const rows = page.content || []
    const items = rows.map((r) => ({
      id: r.id,
      name: r.pkgName || r.url || `安装包 #${r.id}`,
      android_package: '',
      ios_bundle_id: '',
      platform: r.platform
    }))
    return { success: true, data: { items, total: items.length }, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message, data: { items: [] } }
  }
}

export async function createAppTestApplication(_sonicProjectId, _data) {
  return {
    success: false,
    message: '请在 Sonic 控制台上传安装包，刷新下方「测试应用」列表后选择'
  }
}

export async function updateAppTestApplication() {
  return { success: false, message: '不支持，请在 Sonic 控制台修改' }
}

export async function deleteAppTestApplication() {
  return { success: false, message: '不支持，请在 Sonic 控制台删除' }
}

async function moduleNameMapForProject(sonicProjectId) {
  const res = await listAppTestModules(sonicProjectId)
  const m = {}
  for (const it of res.data?.items || []) {
    m[it.id] = it.name
  }
  return m
}

/** 同一 Sonic 项目下合并并发、短时缓存，避免列表页同时 fetchModules 与 listAppTestCases 各打一次 modules/list */
const MODULES_LIST_TTL_MS = 60_000
const modulesListInflight = new Map()
const modulesListCache = new Map()

export function invalidateSonicModulesListCache(sonicProjectId) {
  const k = Number(sonicProjectId)
  if (Number.isFinite(k) && k > 0) modulesListCache.delete(k)
  else modulesListCache.clear()
}

function cloneModuleItems(items) {
  return (items || []).map((it) => ({
    ...it,
    pages: Array.isArray(it.pages) ? it.pages.map((p) => ({ ...p })) : []
  }))
}

export async function listAppTestModules(sonicProjectId) {
  if (!sonicProjectId) return { ...noSonicProject(), data: { items: [] } }
  const key = Number(sonicProjectId)
  const now = Date.now()
  const hit = modulesListCache.get(key)
  if (hit && now - hit.at < MODULES_LIST_TTL_MS) {
    const items = cloneModuleItems(hit.items)
    return { success: true, data: { items, total: items.length }, message: 'ok' }
  }
  let pending = modulesListInflight.get(key)
  if (pending) return pending

  pending = (async () => {
    try {
      const resp = await sonicHttp.get('/controller/modules/list', {
        params: { projectId: sonicProjectId }
      })
      const rows = Array.isArray(resp.data) ? resp.data : []
      const items = rows.map((r) => ({
        id: r.id,
        name: r.projectName || r.name,
        project: sonicProjectId,
        pageCount: Number.isFinite(Number(r.pageCount)) ? Number(r.pageCount) : 0,
        pages: Array.isArray(r.pages)
          ? r.pages.map((p) => ({
              id: p.id,
              name: p.name,
              sortOrder: Number.isFinite(Number(p.sortOrder)) ? Number(p.sortOrder) : 0
            }))
          : []
      }))
      modulesListCache.set(key, { at: Date.now(), items })
      const out = cloneModuleItems(items)
      return { success: true, data: { items: out, total: out.length }, message: 'ok' }
    } catch (e) {
      return { success: false, message: e.message, data: { items: [] } }
    } finally {
      modulesListInflight.delete(key)
    }
  })()

  modulesListInflight.set(key, pending)
  return pending
}

/** Sonic element_pages：挂在模块下，用于 PUT /controller/elements 的 pageId */
export async function listSonicElementPages(sonicProjectId, moduleId) {
  if (!sonicProjectId || moduleId == null || Number(moduleId) <= 0) {
    return { success: true, data: { items: [] } }
  }
  try {
    const resp = await sonicHttp.get('/controller/elementPages/list', {
      params: { projectId: sonicProjectId, moduleId: Number(moduleId) }
    })
    const rows = Array.isArray(resp.data) ? resp.data : []
    return { success: true, data: { items: rows }, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message, data: { items: [] } }
  }
}

/** Sonic element_pages：按模块名查询（同名模块会合并返回） */
export async function listSonicElementPagesByModuleName(sonicProjectId, moduleName) {
  const name = String(moduleName || '').trim()
  if (!sonicProjectId || !name) {
    return { success: true, data: { items: [] } }
  }
  try {
    const resp = await sonicHttp.get('/controller/elementPages/listByModuleName', {
      params: { projectId: sonicProjectId, moduleName: name }
    })
    const rows = Array.isArray(resp.data) ? resp.data : []
    return { success: true, data: { items: rows }, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message, data: { items: [] } }
  }
}

/** Sonic elements：按页面查询元素列表 */
export async function listSonicElementsByPage(sonicProjectId, pageId, params = {}) {
  const pid = Number(sonicProjectId || 0)
  const pgid = Number(pageId || 0)
  if (!pid || !pgid) {
    return { success: true, data: { items: [], total: 0 }, message: 'ok' }
  }
  try {
    const resp = await sonicHttp.get('/controller/elements/list', {
      params: {
        projectId: pid,
        pageIds: [pgid],
        page: params.page || 1,
        pageSize: params.pageSize || 200
      }
    })
    const page = resp.data || {}
    const rows = Array.isArray(page.content) ? page.content : []
    return {
      success: true,
      data: {
        items: rows,
        total: Number(page.totalElements || rows.length || 0)
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message, data: { items: [], total: 0 } }
  }
}

/** Sonic element_pages：创建页面 */
export async function createSonicElementPage(sonicProjectId, payload = {}) {
  const pid = Number(sonicProjectId || 0)
  const moduleId = Number(payload.moduleId || 0)
  const name = String(payload.name || '').trim()
  if (!pid || !moduleId || !name) {
    return { success: false, message: '参数不完整' }
  }
  try {
    await sonicHttp.put('/controller/elementPages', {
      id: null,
      projectId: pid,
      moduleId,
      name,
      sortOrder: Number(payload.sortOrder || 0)
    })
    invalidateSonicModulesListCache(pid)
    const resp = await sonicHttp.get('/controller/elementPages/list', {
      params: { projectId: pid, moduleId }
    })
    const rows = Array.isArray(resp.data) ? resp.data : []
    const created = [...rows]
      .reverse()
      .find((x) => String(x?.name || '').trim() === name) || null
    return { success: true, data: created, message: '创建成功' }
  } catch (e) {
    return { success: false, message: e.message || '创建失败' }
  }
}

/** Sonic element_pages：更新页面 */
export async function updateSonicElementPage(sonicProjectId, payload = {}) {
  const pid = Number(sonicProjectId || 0)
  const id = Number(payload.id || 0)
  const moduleId = Number(payload.moduleId || 0)
  const name = String(payload.name || '').trim()
  if (!pid || !id || !moduleId || !name) {
    return { success: false, message: '参数不完整' }
  }
  try {
    await sonicHttp.put('/controller/elementPages', {
      id,
      projectId: pid,
      moduleId,
      name,
      sortOrder: Number(payload.sortOrder || 0)
    })
    invalidateSonicModulesListCache(pid)
    return { success: true, message: '更新成功' }
  } catch (e) {
    return { success: false, message: e.message || '更新失败' }
  }
}

/** Sonic element_pages：删除页面（sonicProjectId 用于失效 modules/list 短时缓存，避免左侧树仍显示已删页面） */
export async function deleteSonicElementPage(pageId, sonicProjectId = null) {
  const id = Number(pageId || 0)
  if (!id) return { success: false, message: '页面 id 无效' }
  try {
    await sonicHttp.delete('/controller/elementPages', { params: { id } })
    const sp = Number(sonicProjectId || 0)
    if (Number.isFinite(sp) && sp > 0) invalidateSonicModulesListCache(sp)
    return { success: true, message: '删除成功' }
  } catch (e) {
    return { success: false, message: e.message || '删除失败' }
  }
}

/** Sonic elements：更新元素 */
export async function updateSonicElement(payload = {}) {
  const id = Number(payload.id || 0)
  const projectId = Number(payload.projectId || 0)
  const moduleId = Number(payload.moduleId || 0)
  const pageId = Number(payload.pageId || 0)
  const eleName = String(payload.eleName || '').trim()
  const eleType = String(payload.eleType || 'xpath').trim() || 'xpath'
  const eleValue = String(payload.eleValue || '').trim()
  if (!id || !projectId || !moduleId || !pageId || !eleName || !eleValue) {
    return { success: false, message: '参数不完整' }
  }
  try {
    await sonicHttp.put('/controller/elements', {
      id,
      projectId,
      moduleId,
      pageId,
      eleName,
      eleType,
      eleValue
    })
    return { success: true, message: '更新成功' }
  } catch (e) {
    return { success: false, message: e.message || '更新失败' }
  }
}

/** Sonic elements：创建元素 */
export async function createSonicElement(payload = {}) {
  const projectId = Number(payload.projectId || 0)
  const moduleId = Number(payload.moduleId || 0)
  const pageId = Number(payload.pageId || 0)
  const eleName = String(payload.eleName || '').trim()
  const eleType = String(payload.eleType || 'xpath').trim() || 'xpath'
  const eleValue = String(payload.eleValue || '').trim()
  if (!projectId || !moduleId || !pageId || !eleName || !eleValue) {
    return { success: false, message: '参数不完整' }
  }
  try {
    await sonicHttp.put('/controller/elements', {
      id: null,
      projectId,
      moduleId,
      pageId,
      eleName,
      eleType,
      eleValue
    })
    return { success: true, message: '创建成功' }
  } catch (e) {
    return { success: false, message: e.message || '创建失败' }
  }
}

/** Sonic elements：删除元素 */
export async function deleteSonicElement(elementId) {
  const id = Number(elementId || 0)
  if (!id) return { success: false, message: '元素 id 无效' }
  try {
    await sonicHttp.delete('/controller/elements', { params: { id } })
    return { success: true, message: '删除成功' }
  } catch (e) {
    return { success: false, message: e.message || '删除失败' }
  }
}

export async function createAppTestModule(sonicProjectId, data) {
  if (!sonicProjectId) return noSonicProject()
  const name = String(data?.name || '').trim()
  if (!name) return { success: false, message: '模块名称不能为空' }
  try {
    await sonicHttp.put('/controller/modules', {
      id: null,
      projectId: sonicProjectId,
      name
    })
    invalidateSonicModulesListCache(sonicProjectId)
    const res = await listAppTestModules(sonicProjectId)
    const found = (res.data?.items || []).find((x) => x.name === name)
    return { success: true, data: found || { id: null, name }, message: '创建模块成功' }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

export async function updateAppTestModule(sonicProjectId, id, data) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const info = await sonicHttp.get('/controller/modules', { params: { id } })
    const cur = info.data || {}
    await sonicHttp.put('/controller/modules', {
      ...cur,
      id,
      projectId: sonicProjectId,
      name: String(data?.name ?? cur.name ?? '').trim() || cur.name
    })
    invalidateSonicModulesListCache(sonicProjectId)
    return { success: true, data: { id, ...data }, message: '更新成功' }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

export async function deleteAppTestModule(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  try {
    await sonicHttp.delete('/controller/modules', { params: { id } })
    invalidateSonicModulesListCache(sonicProjectId)
    return { success: true, data: null, message: '已删除' }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

/** 合并同一查询参数的并发 testCases/list（多 watcher / 严格模式重复挂载时只发一次 HTTP） */
const testCasesListInflight = new Map()

function testCasesListRequestKey(sonicProjectId, params) {
  const plat = params.platform != null && params.platform !== '' ? String(params.platform) : 'both'
  const page = params.page || 1
  const pageSize = params.pageSize || 500
  const name = String(params.search || params.name || '').trim()
  const modId = params.module_id != null && params.module_id !== '' ? String(params.module_id) : ''
  return `${sonicProjectId}|${plat}|${page}|${pageSize}|${name}|${modId}`
}

export async function listAppTestCases(sonicProjectId, params = {}) {
  if (!sonicProjectId) return { ...noSonicProject(), data: { items: [] } }
  const reqKey = testCasesListRequestKey(sonicProjectId, params)
  const pending = testCasesListInflight.get(reqKey)
  if (pending) return pending

  const work = (async () => {
    try {
      const modMap = await moduleNameMapForProject(sonicProjectId)
      const commonParams = {
        projectId: sonicProjectId,
        page: params.page || 1,
        pageSize: params.pageSize || 500,
        name: params.search || params.name,
        moduleIds: params.module_id ? [params.module_id] : undefined
      }

      // Sonic 的 testCases/list 在多数版本要求 platform（1/2）必传。
      // 当前页未指定平台时，分别拉 Android/iOS 并合并，避免 4001 缺参。
      let rows = []
      let total = 0
      if (params.platform) {
        const resp = await sonicHttp.get('/controller/testCases/list', {
          params: { ...commonParams, platform: platformToSonicInt(params.platform) }
        })
        const page = resp.data || {}
        rows = page.content || []
        total = page.totalElements ?? rows.length
      } else {
        const [androidResp, iosResp] = await Promise.all([
          sonicHttp.get('/controller/testCases/list', {
            params: { ...commonParams, platform: 1 }
          }),
          sonicHttp.get('/controller/testCases/list', {
            params: { ...commonParams, platform: 2 }
          })
        ])
        const aPage = androidResp.data || {}
        const iPage = iosResp.data || {}
        const aRows = aPage.content || []
        const iRows = iPage.content || []
        const merged = [...aRows, ...iRows]
        const seen = new Set()
        rows = merged.filter((r) => {
          const id = Number(r?.id || 0)
          if (!id || seen.has(id)) return false
          seen.add(id)
          return true
        })
        total = (aPage.totalElements ?? aRows.length) + (iPage.totalElements ?? iRows.length)
      }

      const items = rows.map((r) => mapSonicCaseToAits(r, modMap))
      return {
        success: true,
        data: { items, total: total || items.length },
        message: 'ok'
      }
    } catch (e) {
      return { success: false, message: e.message, data: { items: [] } }
    } finally {
      testCasesListInflight.delete(reqKey)
    }
  })()

  testCasesListInflight.set(reqKey, work)
  return work
}

export async function getAppTestCase(sonicProjectId, id, options = {}) {
  if (!sonicProjectId) return noSonicProject()
  const skipModuleMap = options.skipModuleMap === true
  try {
    const resp = await sonicHttp.get('/controller/testCases', { params: { id } })
    const row = resp.data || {}
    const modMap = skipModuleMap ? {} : await moduleNameMapForProject(sonicProjectId)
    const base = mapSonicCaseToAits(row, modMap)
    const stepsRes = await listAppTestSteps(sonicProjectId, id)
    const flat = flattenStepsTree(stepsRes.data?.items || [])
    return {
      success: true,
      data: {
        ...base,
        sonic_steps: flat,
        steps: flat
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

export async function createAppTestCase(sonicProjectId, payload) {
  if (!sonicProjectId) return noSonicProject()
  const plat = platformToSonicInt(payload.platform)
  try {
    const putRes = await sonicHttp.put('/controller/testCases', {
      id: null,
      name: payload.title?.trim(),
      platform: plat,
      projectId: sonicProjectId,
      moduleId: payload.module ?? payload.module_id ?? 0,
      version: 'aits',
      designer: 'AITS',
      des: (payload.description || ' ').toString().slice(0, 2000) || ' '
    })
    const caseRow = putRes.data || {}
    let sonicCaseId = Number(caseRow.id)
    if (!sonicCaseId) {
      const found = await sonicHttp.get('/controller/testCases/list', {
        params: {
          projectId: sonicProjectId,
          platform: plat,
          name: payload.title?.trim(),
          page: 1,
          pageSize: 5
        }
      })
      const page = found.data || {}
      const rows = page.content || []
      const hit = rows.find((r) => r.name === payload.title?.trim())
      sonicCaseId = hit ? Number(hit.id) : 0
    }
    if (!sonicCaseId) {
      return { success: false, message: '创建用例后未能解析 ID' }
    }
    const hasStepPayload =
      Object.prototype.hasOwnProperty.call(payload, 'sonic_steps') ||
      Object.prototype.hasOwnProperty.call(payload, 'steps')
    const steps = hasStepPayload ? payload.sonic_steps ?? payload.steps : undefined
    if (hasStepPayload && Array.isArray(steps)) {
      await syncStepsToSonicCase(sonicProjectId, sonicCaseId, plat, steps)
    }
    return {
      success: true,
      data: mapSonicCaseToAits({ ...caseRow, id: sonicCaseId }, {}),
      message: putRes.message || '创建成功'
    }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

export async function updateAppTestCase(sonicProjectId, id, payload) {
  if (!sonicProjectId) return noSonicProject()
  const plat = platformToSonicInt(payload.platform)
  try {
    const cur = await sonicHttp.get('/controller/testCases', { params: { id } })
    const row = cur.data || {}
    await sonicHttp.put('/controller/testCases', {
      ...row,
      id,
      name: payload.title?.trim() ?? row.name,
      platform: plat,
      projectId: sonicProjectId,
      moduleId: payload.module ?? payload.module_id ?? row.moduleId ?? 0,
      version: row.version || 'aits',
      designer: row.designer || 'AITS',
      des: (payload.description ?? row.des ?? ' ').toString().slice(0, 2000) || ' '
    })
    const hasStepPayload =
      Object.prototype.hasOwnProperty.call(payload, 'sonic_steps') ||
      Object.prototype.hasOwnProperty.call(payload, 'steps')
    const steps = hasStepPayload ? payload.sonic_steps ?? payload.steps : undefined
    if (hasStepPayload && Array.isArray(steps)) {
      await syncStepsToSonicCase(sonicProjectId, Number(id), plat, steps)
    }
    return {
      success: true,
      data: mapSonicCaseToAits({ ...row, id, name: payload.title, des: payload.description, moduleId: payload.module ?? row.moduleId, platform: plat }, {}),
      message: '更新成功'
    }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

export async function deleteAppTestCase(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  await sonicHttp.delete('/controller/testCases', { params: { id } })
  return { success: true, data: null, message: '已删除' }
}

export async function copyAppTestCase(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  await sonicHttp.get('/controller/testCases/copy', { params: { id } })
  return { success: true, data: null, message: '已复制' }
}

export async function reorderAppTestCases() {
  return { success: false, message: 'Sonic 侧请使用官方客户端调整顺序' }
}

export async function listAppTestSteps(sonicProjectId, caseId) {
  if (!sonicProjectId) return noSonicProject()
  const pl = await sonicHttp.get('/controller/steps/listAll', { params: { caseId } })
  const raw = pl.data
  const items = Array.isArray(raw) ? flattenStepsTree(raw) : []
  return { success: true, data: { items }, message: 'ok' }
}

export async function saveAppTestStep(sonicProjectId, data) {
  const body = data?.step || data
  const caseId = data?.case_id ?? body?.caseId
  if (!sonicProjectId || !caseId) return noSonicProject()
  await sonicHttp.put('/controller/steps', { ...body, projectId: sonicProjectId, caseId })
  return { success: true, data: { item: body }, message: '保存成功' }
}

export async function deleteAppTestStep(sonicProjectId, caseId, id) {
  if (!sonicProjectId) return noSonicProject()
  await sonicHttp.delete('/controller/steps', { params: { id } })
  return { success: true, data: null, message: '已删除' }
}

export async function switchAppTestStep(sonicProjectId, data) {
  await sonicHttp.get('/controller/steps/switchStep', {
    params: { caseId: data.case_id, id: data.id }
  })
  return { success: true, data: {}, message: 'ok' }
}

export async function sortAppTestSteps(sonicProjectId, data) {
  await sonicHttp.put('/controller/steps/stepSort', {
    caseId: data.case_id,
    stepIds: data.step_ids
  })
  return { success: true, data: {}, message: 'ok' }
}

export async function runAppTestCase(sonicProjectId, caseId, data = {}) {
  if (!sonicProjectId) return noSonicProject()
  try {
    let platform = data.case_platform || data.device_platform || ''
    if (!platform) {
      const c = await getAppTestCase(sonicProjectId, caseId, { skipModuleMap: true })
      if (!c.success) return c
      platform = c.data?.platform || 'android'
    }
    const platformInt = platformToSonicInt(platform)
    const deviceIdNum = Number(data.device_id)
    const udId = data.device_udid != null ? String(data.device_udid) : ''
    const ret = await sonicHttp.get('/controller/testCases/runCase', {
      params: {
        id: Number(caseId),
        platform: platformInt,
        ...(Number.isFinite(deviceIdNum) && deviceIdNum > 0 ? { deviceId: deviceIdNum } : {}),
        ...(udId ? { udId } : {})
      }
    })
    const sonicResultId = ret?.data != null ? String(ret.data) : ''
    return {
      success: true,
      data: {
        run_id: sonicResultId,
        sonic_result_id: sonicResultId,
        case_id: caseId,
        platform,
        device_id: data.device_id,
        status: 'running'
      },
      message: '执行请求已提交'
    }
  } catch (e) {
    return { success: false, message: e.message || '执行失败' }
  }
}

function mapSonicSuiteToAits(row) {
  const platformNum = Number(row?.platform || 1)
  const platform = platformNum === 2 ? 'ios' : 'android'
  const suiteCases = Array.isArray(row?.testCases) ? row.testCases : []
  const suiteDevices = Array.isArray(row?.devices) ? row.devices : []
  const createdAt = row?.createTime ?? row?.create_time ?? row?.editTime ?? null
  return {
    id: Number(row?.id || 0),
    name: row?.name || '',
    description: row?.description || row?.des || '',
    status: Number(row?.status ?? 1),
    platform,
    platform_num: platformNum,
    cover: Number(row?.cover || 1),
    test_cases_count: suiteCases.length,
    device_count: suiteDevices.length,
    test_cases: suiteCases,
    devices: suiteDevices,
    created_at: createdAt,
    raw: row
  }
}

export async function listAppTestSuites(sonicProjectId, params = {}) {
  if (!sonicProjectId) return { ...noSonicProject(), data: { items: [], total: 0 } }
  try {
    const resp = await sonicHttp.get('/controller/testSuites/list', {
      params: {
        projectId: sonicProjectId,
        name: params.search || params.name || '',
        page: params.page || 1,
        pageSize: params.pageSize || 50
      }
    })
    const page = resp?.data || {}
    const rows = Array.isArray(page.content) ? page.content : []
    const items = rows.map(mapSonicSuiteToAits)
    return {
      success: true,
      data: {
        items,
        total: Number(page.totalElements || items.length || 0)
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取测试套件失败', data: { items: [], total: 0 } }
  }
}

export async function getAppTestSuite(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/testSuites', { params: { id: Number(id) } })
    return { success: true, data: mapSonicSuiteToAits(resp?.data || {}), message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message || '获取测试套件详情失败' }
  }
}

export async function saveAppTestSuite(sonicProjectId, payload = {}) {
  if (!sonicProjectId) return noSonicProject()
  const id = Number(payload.id || 0)
  const platformNum = payload.platform === 'ios' ? 2 : 1
  const testCases = (payload.testCases || [])
    .map((x) => Number(x?.id || x))
    .filter((x) => Number.isFinite(x) && x > 0)
    .map((x) => ({ id: x }))
  const devices = (payload.devices || [])
    .map((x) => Number(x?.id || x))
    .filter((x) => Number.isFinite(x) && x > 0)
    .map((x) => ({ id: x }))
  const desRaw = payload.des ?? payload.description
  const des =
    desRaw != null && String(desRaw).trim()
      ? String(desRaw).trim().slice(0, 2000)
      : ' '
  try {
    const resp = await sonicHttp.put('/controller/testSuites', {
      id: id > 0 ? id : null,
      name: String(payload.name || '').trim(),
      platform: platformNum,
      cover: Number(payload.cover || 1),
      projectId: sonicProjectId,
      des,
      isOpenPerfmon: Number(payload.isOpenPerfmon || 0),
      perfmonInterval: Number(payload.perfmonInterval || 1000),
      testCases,
      devices
    })
    const body = resp?.data
    let resolvedId = id > 0 ? id : Number(body?.id ?? body)
    if (!Number.isFinite(resolvedId) || resolvedId <= 0) {
      const name = String(payload.name || '').trim()
      if (name) {
        const listRes = await listAppTestSuites(sonicProjectId, { search: name, page: 1, pageSize: 20 })
        const hit = (listRes.data?.items || []).find((s) => s.name === name)
        if (hit?.id) resolvedId = Number(hit.id)
      }
    }
    return {
      success: true,
      data: { id: Number.isFinite(resolvedId) && resolvedId > 0 ? resolvedId : id },
      message: id > 0 ? '更新成功' : '创建成功'
    }
  } catch (e) {
    return { success: false, message: e.message || (id > 0 ? '更新失败' : '创建失败') }
  }
}

export async function deleteAppTestSuite(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  try {
    await sonicHttp.delete('/controller/testSuites', { params: { id: Number(id) } })
    return { success: true, message: '删除成功' }
  } catch (e) {
    return { success: false, message: e.message || '删除失败' }
  }
}

export async function executeAppTestSuite(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/testSuites/runSuite', {
      params: { id: Number(id) }
    })
    const sonicResultId = resp?.data != null ? String(resp.data) : ''
    return {
      success: true,
      data: {
        resultId: sonicResultId,
        sonic_result_id: sonicResultId
      },
      message: '执行请求已提交'
    }
  } catch (e) {
    return { success: false, message: e.message || '执行失败' }
  }
}

function mapResultsListRowToRunItem(r) {
  if (!r || typeof r !== 'object') return null
  const suiteName = r.suiteName ?? r.suite_name ?? ''
  const caseName = r.caseName ?? r.case_name ?? ''
  const suiteId = Number(r.suiteId ?? r.suite_id ?? 0)
  /** Sonic：优先使用后端 executionType（CASE/SUITE），否则按 suite_id 推断 */
  const execType = String(r.executionType ?? r.execution_type ?? '').toUpperCase()
  const isSuiteRun =
    execType === 'SUITE'
      ? true
      : execType === 'CASE'
        ? false
        : Number.isFinite(suiteId) && suiteId > 0
  const runKind = isSuiteRun ? 'suite' : 'case'
  const rawName = String(suiteName || caseName || '').trim()
  const runName = rawName || (isSuiteRun ? `套件 #${suiteId}` : `用例 #${r.id}`)

  return {
    id: r.id,
    case_id: r.caseId ?? r.case_id,
    run_kind: runKind,
    run_name: runName,
    /** 兼容旧列：与 run_name 一致（不含类型前缀） */
    case_title: runName,
    suite_id: isSuiteRun ? suiteId : null,
    device_id: r.rid ? String(r.rid) : '',
    device_udid: '',
    device_name: '',
    device_platform: '',
    status: mapResultStatus(r.status),
    sonic_result_id: String(r.id),
    error_message: '',
    started_at: r.createTime ?? r.create_time,
    finished_at: r.endTime ?? r.end_time,
    created_at: r.createTime ?? r.create_time,
    updated_at: r.endTime ?? r.end_time,
    sonic_raw: r
  }
}

export async function listAppTestRuns(sonicProjectId, params = {}) {
  if (!sonicProjectId) return { ...noSonicProject(), data: { items: [] } }
  try {
    const resp = await sonicHttp.get('/controller/results/list', {
      params: {
        projectId: sonicProjectId,
        page: params.page || 1,
        pageSize: params.pageSize || 100
      }
    })
    const raw = resp?.data
    const page =
      raw && typeof raw === 'object' && !Array.isArray(raw)
        ? raw
        : {}
    const rows = page.content || page.records || (Array.isArray(raw) ? raw : [])
    const items = rows.map(mapResultsListRowToRunItem).filter(Boolean)
    return {
      success: true,
      data: {
        items,
        total: page.totalElements ?? page.total ?? items.length
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message, data: { items: [] } }
  }
}

function mapResultStatus(statusVal) {
  if (typeof statusVal === 'number') {
    return { 0: 'running', 1: 'passed', 2: 'passed', 3: 'failed' }[statusVal] || 'running'
  }
  const s = String(statusVal || '').toUpperCase()
  if (s === 'PASS' || s === 'PASSED') return 'passed'
  if (s === 'FAIL' || s === 'FAILED') return 'failed'
  if (s === 'RUNNING') return 'running'
  return 'pending'
}

export async function getAppTestRun(sonicProjectId, id) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/results', { params: { id } })
    const d = resp.data || {}
    return {
      success: true,
      data: {
        id: d.id,
        status: mapResultStatus(d.status),
        raw_status: d.status,
        case_id: d.caseId,
        sonic_result_id: String(d.id),
        raw: d
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message }
  }
}

export async function refreshAppTestRun(sonicProjectId, id) {
  return getAppTestRun(sonicProjectId, id)
}

function normalizeResultCaseStatusRows(rows) {
  const source = Array.isArray(rows) ? rows : []
  return source.map((row) => {
    const caseObj = row?.case || {}
    return {
      status: Number(row?.status ?? 0),
      startTime: row?.startTime || '',
      endTime: row?.endTime || '',
      case: {
        id: Number(caseObj?.id || row?.caseId || 0),
        name: caseObj?.name || row?.caseName || `用例 #${caseObj?.id || row?.caseId || '-'}`
      },
      device: Array.isArray(row?.device) ? row.device : []
    }
  })
}

function normalizeResultDetailRows(rows) {
  const source = Array.isArray(rows) ? rows : []
  return source.map((row) => ({
    id: row?.id ?? null,
    caseId: Number(row?.caseId || 0),
    resultId: Number(row?.resultId || 0),
    deviceId: String(row?.deviceId ?? ''),
    status: Number(row?.status ?? 0),
    stepId: row?.stepId ?? null,
    des: row?.des || '',
    time: row?.time || '',
    createTime: row?.createTime || '',
    log: row?.log ?? '',
    type: row?.type || ''
  }))
}

export async function getAppRunCaseStatus(sonicProjectId, resultId) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/results/findCaseStatus', {
      params: { id: Number(resultId) }
    })
    return {
      success: true,
      data: { items: normalizeResultCaseStatusRows(resp?.data) },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取报告用例状态失败', data: { items: [] } }
  }
}

export async function listAppRunResultDetails(sonicProjectId, params = {}) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/resultDetail/list', {
      params: {
        caseId: Number(params.caseId),
        resultId: Number(params.resultId),
        deviceId: params.deviceId,
        type: params.type || 'step',
        page: Number(params.page || 1)
      }
    })
    const page = resp?.data || {}
    return {
      success: true,
      data: {
        items: normalizeResultDetailRows(page.content || []),
        totalPages: Number(page.totalPages || 0),
        totalElements: Number(page.totalElements || 0)
      },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取执行步骤失败', data: { items: [], totalPages: 0 } }
  }
}

export async function listAppRunResultDetailsAll(sonicProjectId, params = {}) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/resultDetail/listAll', {
      params: {
        caseId: Number(params.caseId),
        resultId: Number(params.resultId),
        deviceId: params.deviceId,
        type: params.type || 'step'
      }
    })
    return {
      success: true,
      data: { items: normalizeResultDetailRows(resp?.data || []) },
      message: 'ok'
    }
  } catch (e) {
    return { success: false, message: e.message || '获取执行明细失败', data: { items: [] } }
  }
}

export async function listDevicesByIds(sonicProjectId, ids = []) {
  if (!sonicProjectId) return noSonicProject()
  const normalizedIds = (ids || []).map((x) => Number(x)).filter((x) => Number.isFinite(x) && x > 0)
  if (!normalizedIds.length) return { success: true, data: { items: [] }, message: 'ok' }
  try {
    const resp = await sonicHttp.get('/controller/devices/findByIdIn', {
      params: { ids: normalizedIds }
    })
    const rawRows = Array.isArray(resp?.data) ? resp.data : []
    const items = rawRows.map((r) => ({
      id: Number(r?.id || 0),
      model: r?.model || r?.name || `设备 #${r?.id || '-'}`,
      platform: Number(r?.platform || 0),
      name: r?.name || '',
      udId: r?.udId || r?.udid || ''
    }))
    return { success: true, data: { items }, message: 'ok' }
  } catch (e) {
    return { success: false, message: e.message || '获取设备信息失败', data: { items: [] } }
  }
}

// 停止指定测试运行（使用 Sonic 的 forceStopSuite）
// resultId 对应 sonic-server results 表的 id（AITS 运行记录里的 id）
export async function forceStopAppTestRun(sonicProjectId, resultId) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.get('/controller/testSuites/forceStopSuite', {
      params: { resultId }
    })
    return resp?.code === 2000
      ? { success: true, data: null, message: resp?.message || '已停止' }
      : { success: false, message: resp?.message || '停止失败', data: null }
  } catch (e) {
    return { success: false, message: e?.response?.data?.message || e?.message || '停止失败', data: null }
  }
}

// 删除指定测试执行记录（results）
export async function deleteAppTestRun(sonicProjectId, resultId) {
  if (!sonicProjectId) return noSonicProject()
  try {
    const resp = await sonicHttp.delete('/controller/results', { params: { id: resultId } })
    return resp?.code === 2000
      ? { success: true, data: null, message: resp?.message || '已删除' }
      : { success: false, message: resp?.message || '删除失败', data: null }
  } catch (e) {
    return { success: false, message: e?.response?.data?.message || e?.message || '删除失败', data: null }
  }
}
