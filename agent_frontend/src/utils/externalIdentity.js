const DEFAULT_USER_ID = 'admin'

let cachedIdentity = null

function normalizeIdentity(identity) {
  if (!identity) return null

  const userId = String(identity.userId || '').trim()
  if (!userId) return null

  const displayName = String(identity.displayName || '').trim() || userId
  const ts = String(identity.ts || '').trim()
  const sign = String(identity.sign || '').trim()

  return {
    userId,
    displayName,
    ts,
    sign,
  }
}

export function readExternalIdentityFromLocation() {
  const params = new URLSearchParams(window.location.search)
  const userId = params.get('user') || params.get('lognum') || ''
  const displayName = params.get('name') || userId || ''
  const ts = params.get('ts') || ''
  const sign = params.get('sign') || ''

  return normalizeIdentity({ userId, displayName, ts, sign })
}

export function setExternalIdentity(identity) {
  cachedIdentity = normalizeIdentity(identity)
  return cachedIdentity
}

export function getExternalIdentity() {
  if (cachedIdentity) {
    return cachedIdentity
  }
  cachedIdentity = readExternalIdentityFromLocation()
  return cachedIdentity
}

export function getExternalUserId() {
  return getExternalIdentity()?.userId || DEFAULT_USER_ID
}

export function getExternalDisplayName() {
  const identity = getExternalIdentity()
  return identity?.displayName || identity?.userId || DEFAULT_USER_ID
}

export function buildExternalAuthHeaders() {
  const identity = getExternalIdentity()
  if (!identity) {
    return {}
  }

  const headers = {
    'X-External-User': identity.userId,
  }

  if (identity.ts) {
    headers['X-External-Ts'] = identity.ts
  }
  if (identity.sign) {
    headers['X-External-Sign'] = identity.sign
  }
  return headers
}

export function fetchWithExternalAuth(input, init = {}) {
  const headers = new Headers(init.headers || {})
  const externalHeaders = buildExternalAuthHeaders()

  Object.entries(externalHeaders).forEach(([key, value]) => {
    headers.set(key, value)
  })

  return fetch(input, {
    ...init,
    headers,
  })
}

export function appendExternalAuthParams(rawUrl) {
  if (!rawUrl) return rawUrl

  const identity = getExternalIdentity()
  if (!identity?.userId || !identity.ts || !identity.sign) {
    return rawUrl
  }

  const url = new URL(rawUrl, window.location.origin)
  url.searchParams.set('user', identity.userId)
  url.searchParams.set('ts', identity.ts)
  url.searchParams.set('sign', identity.sign)
  return `${url.pathname}${url.search}${url.hash}`
}
