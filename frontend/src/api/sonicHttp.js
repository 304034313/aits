import axios from 'axios'
import qs from 'qs'
import { ElMessage } from 'element-plus'

export const SONIC_TOKEN_KEY = 'SonicToken'
const SONIC_AUTO_USERNAME = import.meta.env.VITE_SONIC_AUTO_USERNAME || 'aits-lemon'
const SONIC_AUTO_PASSWORD = import.meta.env.VITE_SONIC_AUTO_PASSWORD || '123456'
const SONIC_AUTO_LOGIN_ENABLED = String(import.meta.env.VITE_SONIC_AUTO_LOGIN ?? 'true').toLowerCase() !== 'false'

function normalizeToken(raw) {
  if (raw == null) return ''
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (!t) return ''
    // 兼容被 JSON.stringify 过的 token
    if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
      return t.slice(1, -1).trim()
    }
    return t
  }
  if (typeof raw === 'object') {
    // 兼容不同后端返回格式
    const candidate = raw.token || raw.accessToken || raw.sonicToken || raw.data
    return normalizeToken(candidate)
  }
  return String(raw).trim()
}

export function getSonicToken() {
  try {
    return normalizeToken(localStorage.getItem(SONIC_TOKEN_KEY))
  } catch {
    return ''
  }
}

export function setSonicToken(token) {
  const normalized = normalizeToken(token)
  if (normalized) {
    localStorage.setItem(SONIC_TOKEN_KEY, normalized)
  } else {
    localStorage.removeItem(SONIC_TOKEN_KEY)
  }
}

export function clearSonicToken() {
  setSonicToken('')
  // 清理历史遗留 key，避免出现两个 token
  localStorage.removeItem('sonicToken')
}

const baseURL = (import.meta.env.VITE_SONIC_API_BASE || '/sonic-api').replace(/\/$/, '')

const sonicHttp = axios.create({
  baseURL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  },
  withCredentials: true,
  paramsSerializer: (params) =>
    qs.stringify(params || {}, { arrayFormat: 'brackets', skipNulls: true })
})

let sonicAutoLoginPromise = null

function isLoginEndpoint(url = '') {
  return String(url).includes('/controller/users/login')
}

sonicHttp.interceptors.request.use(
  (config) => {
    const token = getSonicToken()
    if (token) {
      config.headers = config.headers || {}
      config.headers.SonicToken = token
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (err) => Promise.reject(err)
)

let sonicAuthRedirecting = false

sonicHttp.interceptors.response.use(
  async (response) => {
    const body = response.data
    if (!body || typeof body !== 'object') {
      return body
    }
    const code = body.code
    if (code === undefined || code === null) {
      return body
    }
    if (code === 2000) {
      return body
    }
    if (code === 1001) {
      const originalConfig = response.config || {}
      clearSonicToken()
      if (!originalConfig._sonicRetried && !originalConfig._sonicSkipAutoRetry && !isLoginEndpoint(originalConfig.url)) {
        originalConfig._sonicRetried = true
        const ok = await ensureSonicSession({ force: true, silent: true })
        if (ok) {
          return sonicHttp(originalConfig)
        }
      }
      if (!sonicAuthRedirecting) {
        sonicAuthRedirecting = true
        ElMessage.warning(body.message || 'Sonic 登录已失效，已尝试自动重新登录')
        window.dispatchEvent(new CustomEvent('aits-sonic-auth-expired'))
        setTimeout(() => {
          sonicAuthRedirecting = false
        }, 1500)
      }
      return Promise.reject(new Error(body.message || 'Sonic 未授权'))
    }
    if (code === 1003) {
      ElMessage.error(body.message || '没有权限')
      return Promise.reject(new Error(body.message || '没有权限'))
    }
    if (body.message) {
      ElMessage.error(body.message)
    }
    return Promise.reject(new Error(body.message || 'Sonic 请求失败'))
  },
  (err) => {
    if (err.response?.status === 503) {
      ElMessage.info('服务就绪中，请稍后重试')
    } else if (!err.message?.includes('Sonic')) {
      ElMessage.error(err.response?.data?.message || err.message || '网络错误')
    }
    return Promise.reject(err)
  }
)

/**
 * Sonic 登录；成功后将 token 写入 localStorage（与 sonic-client-web 一致）
 */
export async function sonicLogin({ userName, password }, options = {}) {
  const body = await sonicHttp.post('/controller/users/login', {
    userName,
    password
  }, {
    _sonicSkipAutoRetry: Boolean(options?.skipAutoRetry)
  })
  const token = normalizeToken(body?.data)
  if (token) setSonicToken(token)
  return body
}

export async function ensureSonicSession(options = {}) {
  if (!SONIC_AUTO_LOGIN_ENABLED) return Boolean(getSonicToken())
  if (!options.force && getSonicToken()) return true
  if (!SONIC_AUTO_USERNAME || !SONIC_AUTO_PASSWORD) return false
  if (!sonicAutoLoginPromise) {
    sonicAutoLoginPromise = (async () => {
      try {
        await sonicLogin(
          { userName: SONIC_AUTO_USERNAME, password: SONIC_AUTO_PASSWORD },
          { skipAutoRetry: true }
        )
        return Boolean(getSonicToken())
      } catch {
        if (!options.silent) {
          ElMessage.error('Sonic 自动登录失败，请检查账号密码')
        }
        return false
      } finally {
        sonicAutoLoginPromise = null
      }
    })()
  }
  return sonicAutoLoginPromise
}

export default sonicHttp
