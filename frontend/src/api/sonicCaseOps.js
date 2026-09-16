import sonicHttp from './sonicHttp'

const SONIC_COVER_CASE = 1

export function platformToSonicInt(platform) {
  const p = String(platform || '').toLowerCase()
  if (p === 'ios') return 2
  return 1
}

function normalizeStepType(stepType) {
  const t = String(stepType || '').trim()
  if (!t) return 'pause'
  if (t === 'back') return 'runBack'
  return t
}

function commentPageRows(payload) {
  const data = payload?.data || {}
  return Array.isArray(data.content) ? data.content : []
}

function collectStepIdsPostOrder(items) {
  const ids = []
  for (const s of items || []) {
    const children = s?.childSteps
    if (Array.isArray(children) && children.length) {
      ids.push(...collectStepIdsPostOrder(children))
    }
    if (s?.id != null) ids.push(Number(s.id))
  }
  return ids
}

export async function clearStepsForCase(caseId) {
  const pl = await sonicHttp.get('/controller/steps/listAll', { params: { caseId } })
  const raw = pl?.data
  const items = Array.isArray(raw) ? raw : []
  for (const sid of collectStepIdsPostOrder(items)) {
    try {
      await sonicHttp.delete('/controller/steps', { params: { id: sid } })
    } catch {
      /* ignore single delete failure */
    }
  }
}

export async function syncStepsToSonicCase(sonicProjectId, sonicCaseId, platformInt, steps) {
  const pl = await sonicHttp.get('/controller/steps/listAll', { params: { caseId: sonicCaseId } })
  const raw = pl?.data
  const treeItems = Array.isArray(raw) ? raw : []
  const existingIds = new Set(
    collectStepIdsPostOrder(treeItems)
      .map((id) => Number(id))
      .filter((id) => id > 0)
  )
  const keptIds = new Set()

  for (let idx = 0; idx < steps.length; idx += 1) {
    const st = steps[idx] || {}
    const normalizedStepType = normalizeStepType(st.stepType)
    const elemsIn = Array.isArray(st.elements) ? st.elements : []
    const elemDtos = []
    for (const ele of elemsIn) {
      const existingId = Number(ele?.id || ele?.element_id || 0)
      const eleType = String(ele.eleType || ele.ele_type || 'xpath')
      const eleValue = String(ele.eleValue || ele.ele_value || ele.locator || '')
      const eleName = String(ele.eleName || ele.ele_name || ele.name || '').trim()
      if (existingId <= 0) {
        throw new Error(`步骤 ${idx + 1} 缺少有效元素 ID，请重新选择页面元素后再保存`)
      }
      elemDtos.push({
        id: existingId,
        eleName,
        eleType,
        eleValue,
        projectId: sonicProjectId
      })
    }
    const disabled = st.disabled ? 1 : 0
    const normalizedContent = (() => {
      const rawC = String(st.content || '').trim()
      if (normalizedStepType === 'pause') return rawC || '1000'
      return rawC
    })()
    const stepId = Number(st.id || 0)
    const useId = stepId > 0 && existingIds.has(stepId) ? stepId : 0
    if (useId > 0) keptIds.add(useId)

    await sonicHttp.put('/controller/steps', {
      id: useId,
      parentId: Number(st.parentId || 0),
      projectId: sonicProjectId,
      publicStepsId: 0,
      caseId: sonicCaseId,
      platform: platformInt,
      stepType: normalizedStepType,
      content: normalizedContent,
      text: String(st.text || ''),
      sort: idx + 1,
      error: Number(st.error || 3),
      conditionType: Number(st.conditionType || 0),
      disabled,
      elements: elemDtos
    })
  }

  const deleteOrder = collectStepIdsPostOrder(treeItems)
  for (const sid of deleteOrder) {
    const id = Number(sid)
    if (id > 0 && !keptIds.has(id)) {
      try {
        await sonicHttp.delete('/controller/steps', { params: { id } })
      } catch {
        /* ignore single delete failure */
      }
    }
  }
}

async function findSuiteByName(projectId, suiteKey) {
  const pl = await sonicHttp.get('/controller/testSuites/list', {
    params: { projectId, name: suiteKey, page: 1, pageSize: 5 }
  })
  const rows = commentPageRows(pl)
  for (const row of rows) {
    if (row.name === suiteKey) return Number(row.id)
  }
  return null
}

async function saveOneCaseSuite(sonicProjectId, platformInt, suiteKey, sonicCaseId, deviceSonicId) {
  let suiteId = await findSuiteByName(sonicProjectId, suiteKey)
  await sonicHttp.put('/controller/testSuites', {
    id: suiteId,
    name: suiteKey,
    platform: platformInt,
    cover: SONIC_COVER_CASE,
    projectId: sonicProjectId,
    isOpenPerfmon: 0,
    perfmonInterval: 1000,
    testCases: [{ id: sonicCaseId }],
    devices: [{ id: deviceSonicId }]
  })
  suiteId = await findSuiteByName(sonicProjectId, suiteKey)
  if (!suiteId) throw new Error('同步 Sonic 测试套件失败')
  return suiteId
}

export async function resolveSonicDeviceId(deviceId, udId) {
  const d = String(deviceId || '').trim()
  if (d && /^\d+$/.test(d)) return Number(d)
  const u = String(udId || '').trim()
  if (!u) throw new Error('缺少有效 device_id 或 UDID')
  const pl = await sonicHttp.get('/controller/devices/list', {
    params: { deviceInfo: u, page: 1, pageSize: 10 }
  })
  const rows = commentPageRows(pl)
  for (const row of rows) {
    if (String(row.udId || row.udid || '') === u) return Number(row.id)
  }
  throw new Error(`Sonic 中未找到 UDID=${u} 的设备`)
}

/**
 * 单用例执行：维护套件并 runSuite（步骤需已在 Sonic 用例上或通过 syncStepsToSonicCase 写入）
 */
export async function runSonicSingleCase({
  sonicProjectId,
  sonicCaseId,
  platformStr,
  deviceId,
  deviceUdid,
  suiteKey
}) {
  const plat = platformToSonicInt(platformStr)
  const key =
    suiteKey || `AITS_SUITE_CASE_${sonicProjectId}_${sonicCaseId}`
  const devSid = await resolveSonicDeviceId(deviceId, deviceUdid)
  const suiteId = await saveOneCaseSuite(sonicProjectId, plat, key, sonicCaseId, devSid)
  const runPl = await sonicHttp.get('/controller/testSuites/runSuite', {
    params: { id: suiteId }
  })
  let resultId = ''
  const rawData = runPl?.data
  if (rawData != null) resultId = String(rawData)
  return {
    sonic_result_id: resultId,
    sonic_suite_id: suiteId,
    raw: runPl
  }
}
