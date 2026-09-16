/**
 * WebUI 用例断言展示（与后端 assertion_display.py 对齐）
 */

const TYPE_LABELS = {
  text_visible: '文本可见',
  text_equals: '文本等于',
  text_contains: '文本包含',
  text_not_exists: '文本不存在',
  url_equals: 'URL等于',
  url_matches: 'URL匹配',
  element_visible: '元素可见',
  element_hidden: '元素隐藏',
  element_enabled: '元素启用',
  element_disabled: '元素禁用',
  attribute_equals: '属性等于',
  count_equals: '数量等于',
  count_at_least: '数量≥',
  network_response: '接口响应',
  vision_assert: '视觉断言',
}

function assertionLabel(item) {
  if (!item || typeof item !== 'object') return ''
  const desc = (item.description || '').trim()
  if (desc) return desc
  const t = item.type
  const expected = item.expected
  if (t === 'vision_assert' && expected) return `视觉：${expected}`
  if (['text_visible', 'text_equals', 'text_contains'].includes(t) && expected) return String(expected)
  if (['url_equals', 'url_matches'].includes(t) && expected) return `URL：${expected}`
  return TYPE_LABELS[t] || t || '断言'
}

function collectStepAssertions(steps) {
  const out = []
  if (!Array.isArray(steps)) return out
  for (const st of steps) {
    if (st && Array.isArray(st.assertions)) {
      out.push(...st.assertions.filter(a => a && typeof a === 'object'))
    }
  }
  return out
}

/** 从行数据或编辑表单构建展示结构 */
export function buildAssertionDisplay({ expectations = [], steps = [], expected_result = '' } = {}) {
  const expList = Array.isArray(expectations) ? expectations : []
  const stepAsserts = collectStepAssertions(steps)
  const caseCnt = expList.length
  const stepCnt = stepAsserts.length
  const all = [...expList, ...stepAsserts]
  const visionCnt = all.filter(a => a.type === 'vision_assert').length
  const hasStructured = caseCnt + stepCnt > 0

  let primary = ''
  if (expList.length) primary = assertionLabel(expList[0])
  else if (stepAsserts.length) primary = assertionLabel(stepAsserts[0])
  else primary = (expected_result || '').trim()

  let chipText = ''
  if (hasStructured) {
    const parts = []
    if (caseCnt) parts.push(`${caseCnt}条用例级`)
    if (stepCnt) parts.push(`${stepCnt}条步骤级`)
    let chip = `断言 ${parts.join(' · ')}`
    if (visionCnt) chip += ` · 🪄${visionCnt}`
    if (primary) {
      const short = primary.length <= 36 ? primary : `${primary.slice(0, 33)}...`
      chipText = `【${short}】 (${chip})`
    } else {
      chipText = chip
    }
  } else if (primary) {
    const short = primary.length <= 40 ? primary : `${primary.slice(0, 37)}...`
    chipText = `【期望：${short}】`
  }

  return {
    case_level_count: caseCnt,
    step_level_count: stepCnt,
    vision_count: visionCnt,
    has_structured: hasStructured,
    primary_label: primary,
    chip_text: chipText,
    tooltip_assertion: primary,
  }
}

/** 列表行：优先用后端 assertion_display，否则本地计算 */
export function getRowAssertionDisplay(row) {
  if (row?.assertion_display && typeof row.assertion_display === 'object') {
    return row.assertion_display
  }
  return buildAssertionDisplay({
    expectations: row?.expectations,
    steps: row?.steps,
    expected_result: row?.expected_result,
  })
}

/** 执行状态 tooltip 用的断言说明 */
export function getAssertionTooltipText(row) {
  const d = getRowAssertionDisplay(row)
  return d.tooltip_assertion || d.primary_label || row?.expected_result || ''
}

/** 列表名称下方 chip */
export function getAssertionChipText(row) {
  const d = getRowAssertionDisplay(row)
  return d.chip_text || ''
}
