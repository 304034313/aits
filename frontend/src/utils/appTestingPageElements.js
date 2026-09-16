/**
 * App 测试「页面 / 元素」本地库（与页面元素管理共用 localStorage）
 */

export const PAGES_STORAGE_PREFIX = 'aits-app-testing-pages-v1'

export function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function normalizeStoredElement(el) {
  if (!el || typeof el !== 'object') {
    return { id: genId(), name: '未命名元素', locator: '' }
  }
  const id = el.id || genId()
  let name = String(el.name ?? '').trim()
  let locator = el.locator != null ? String(el.locator).trim() : ''
  if (!locator) {
    locator = [el.xpath, el.resourceId, el.text]
      .map((s) => String(s || '').trim())
      .filter(Boolean)
      .join(' ')
  }
  if (!name) name = locator ? locator.slice(0, 48) : '未命名元素'
  const locatorType =
    el.locatorType != null && String(el.locatorType).trim()
      ? String(el.locatorType).trim()
      : ''
  return { id, name, locator, ...(locatorType ? { locatorType } : {}) }
}

function normalizePageSonicModuleId(raw) {
  if (raw === undefined || raw === null || raw === '') return undefined
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

function normalizePageSonicPageId(raw) {
  if (raw === undefined || raw === null || raw === '') return undefined
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

export function normalizeStoredPages(data) {
  return (data || [])
    .map((page) => {
      if (!page || typeof page !== 'object') return null
      const id = page.id || genId()
      const name = String(page.name ?? '').trim() || '未命名页面'
      const elements = (page.elements || []).map(normalizeStoredElement)
      const sonicModuleId = normalizePageSonicModuleId(page.sonicModuleId)
      const sonicPageId = normalizePageSonicPageId(page.sonicPageId)
      return {
        id,
        name,
        elements,
        ...(sonicModuleId !== undefined ? { sonicModuleId } : {}),
        ...(sonicPageId !== undefined ? { sonicPageId } : {})
      }
    })
    .filter(Boolean)
}

export function pagesStorageKey(projectId) {
  return `${PAGES_STORAGE_PREFIX}:${projectId}`
}

/** @returns {Array<{ id: string, name: string, elements: Array }>} */
export function loadPagesForProject(projectId) {
  if (!projectId) return []
  try {
    const raw = localStorage.getItem(pagesStorageKey(projectId))
    if (!raw) return []
    const data = JSON.parse(raw)
    if (!Array.isArray(data)) return []
    return normalizeStoredPages(data)
  } catch {
    return []
  }
}

export function savePagesToStorage(projectId, pages) {
  if (!projectId) return
  try {
    localStorage.setItem(pagesStorageKey(projectId), JSON.stringify(pages))
  } catch {
    /* quota / private mode */
  }
}

export const LOCATOR_TYPE_LABELS = {
  id: 'resource-id',
  xpath: 'xpath',
  accessibilityId: 'accessibility id',
  androidUIAutomator: 'UiAutomator',
  point: '坐标'
}

export function locatorTypeLabel(t) {
  const s = t != null ? String(t).trim() : ''
  return s ? (LOCATOR_TYPE_LABELS[s] || s) : '—'
}
