/**
 * 视觉断言：expected（LLM 描述）与 description（Allure 步骤）智能同步
 */

export function visionAutoDescription(expected) {
  const text = (expected || '').trim()
  return text ? `视觉判断：${text}` : ''
}

/** description 是否与自动生成的值不一致（视为用户自定义） */
export function isVisionDescriptionCustom(item) {
  if (!item || item.type !== 'vision_assert') return false
  const desc = (item.description || '').trim()
  if (!desc) return false
  return desc !== visionAutoDescription(item.expected)
}

/** 加载/新增时初始化 touched 并按需同步 description */
export function initVisionDescriptionState(item) {
  if (!item || item.type !== 'vision_assert') return item
  if (item._descriptionTouched !== true && item._descriptionTouched !== false) {
    item._descriptionTouched = isVisionDescriptionCustom(item)
  }
  if (!item._descriptionTouched) {
    item.description = visionAutoDescription(item.expected)
  }
  return item
}

let _syncingVisionDescription = false

export function onVisionExpectedChange(item) {
  if (!item || item.type !== 'vision_assert') return
  if (item._descriptionTouched) return
  _syncingVisionDescription = true
  try {
    item.description = visionAutoDescription(item.expected)
  } finally {
    _syncingVisionDescription = false
  }
}

export function onVisionDescriptionInput(item) {
  if (!item || item.type !== 'vision_assert') return
  if (_syncingVisionDescription) return
  item._descriptionTouched = true
}

export function resetVisionDescriptionState(item) {
  if (!item) return
  item._descriptionTouched = false
}

export function sanitizeAssertionForSave(item) {
  if (!item || typeof item !== 'object') return item
  const { _descriptionTouched, ...rest } = item
  return rest
}

export function sanitizeAssertionsForSave(list) {
  if (!Array.isArray(list)) return []
  return list.map(sanitizeAssertionForSave)
}
