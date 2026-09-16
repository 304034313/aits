export const PACK_PROFILE = 'llm-eval-api'

export const isLlmEvalApiPack = () => PACK_PROFILE === 'llm-eval-api'

export const isModuleEnabled = (module) => {
  if (!isLlmEvalApiPack()) return true
  return module === 'api' || module === 'project'
}

export const isPortalDisabled = (portalId) =>
  isLlmEvalApiPack() && ['portal-web', 'portal-app', 'portal-perf'].includes(portalId)

export const LLM_EVAL_DISABLED_PORTAL_MESSAGE =
  '此模块功能仅对AI赋能班以及AI全栈学员开放，请联系授课老师确认你的权限。'

export const LLM_EVAL_RESTRICTED_PORTAL_IDS = ['portal-web', 'portal-app', 'portal-perf']
