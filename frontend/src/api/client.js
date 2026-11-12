// The access token lives ONLY in memory (not localStorage) so XSS cannot steal a long-lived credential.
// The refresh token is an httpOnly cookie that JS never sees; /auth/refresh uses it to mint a new access token.
const BASE = import.meta.env.VITE_API_BASE || '/api'

let accessToken = null
let onAuthLost = () => {}
let refreshing = null // single-flight: concurrent 401s share one refresh call

export const setAccessToken = (t) => { accessToken = t }
export const getAccessToken = () => accessToken
export const setAuthLostHandler = (fn) => { onAuthLost = fn }

export class ApiError extends Error {
  constructor(status, message, fieldErrors = {}) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

async function parseError(res) {
  let body = null
  try { body = await res.json() } catch { /* not json */ }
  const detail = body?.detail
  if (Array.isArray(detail)) {
    const fieldErrors = {}
    for (const d of detail) {
      const field = d.loc?.[d.loc.length - 1]
      const msg = String(d.msg || 'Invalid value').replace(/^Value error, /, '')
      if (field && !(field in fieldErrors)) fieldErrors[field] = msg
    }
    return new ApiError(res.status, Object.values(fieldErrors)[0] || 'Invalid input', fieldErrors)
  }
  return new ApiError(res.status, typeof detail === 'string' ? detail : `Request failed (${res.status})`)
}

export function refreshSession() {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw await parseError(res)
        const data = await res.json()
        accessToken = data.access_token
        return data
      })
      .finally(() => { refreshing = null })
  }
  return refreshing
}

function raw(path, { method = 'GET', body } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  return fetch(`${BASE}${path}`, {
    method, headers, credentials: 'include',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

export async function api(path, opts = {}) {
  let res
  try { res = await raw(path, opts) } catch { throw new ApiError(0, 'Cannot reach the server. Check your connection.') }
  if (res.status === 401 && !path.startsWith('/auth/')) {
    try {
      await refreshSession()
      res = await raw(path, opts) // transparent retry with the new token
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { accessToken = null; onAuthLost() }
      throw e instanceof ApiError ? e : new ApiError(0, 'Cannot reach the server.')
    }
  }
  if (!res.ok) throw await parseError(res)
  return res.status === 204 ? null : res.json()
}

export const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v) })
  const s = p.toString()
  return s ? `?${s}` : ''
}
