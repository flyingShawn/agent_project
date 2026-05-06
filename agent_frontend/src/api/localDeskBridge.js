import { getExternalDisplayName, getExternalUserId } from '../utils/externalIdentity'

const DEFAULT_BRIDGE_BASE_URL = 'http://127.0.0.1:17891'

function getBridgeBaseUrl() {
  const runtimeConfig = window.__APP_CONFIG__ || {}
  return (
    runtimeConfig.localDeskBridgeUrl ||
    import.meta.env.VITE_LOCAL_DESK_BRIDGE_URL ||
    DEFAULT_BRIDGE_BASE_URL
  ).replace(/\/+$/, '')
}

function buildRequestId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID()
  }
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function buildTimeoutSignal(timeoutMs) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  return { signal: controller.signal, clear: () => window.clearTimeout(timer) }
}

async function fetchJsonWithTimeout(url, init, timeoutMs) {
  const timeout = buildTimeoutSignal(timeoutMs)
  try {
    const response = await fetch(url, {
      ...init,
      mode: 'cors',
      cache: 'no-store',
      signal: timeout.signal,
    })

    if (!response.ok) {
      let message = `HTTP error! status: ${response.status}`
      try {
        const payload = await response.json()
        message = payload.message || payload.detail || message
      } catch (_) {
      }
      throw new Error(message)
    }

    return response.json()
  } finally {
    timeout.clear()
  }
}

export function shouldUseLocalDeskBridge(agentType) {
  const runtimeConfig = window.__APP_CONFIG__ || {}
  const envDisabled = import.meta.env.VITE_LOCAL_DESK_BRIDGE_ENABLED === 'false'
  return agentType === 'desk-agent' && runtimeConfig.localDeskBridgeEnabled !== false && !envDisabled
}

export async function checkLocalDeskBridge() {
  const baseUrl = getBridgeBaseUrl()
  const maxRetries = 2
  let lastError = null

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fetchJsonWithTimeout(`${baseUrl}/api/v1/health`, { method: 'GET' }, 3000)
    } catch (e) {
      lastError = e
      if (attempt < maxRetries) {
        await new Promise(r => setTimeout(r, 500))
      }
    }
  }

  const hint = lastError?.name === 'AbortError'
    ? '连接超时，请确认 XFAgentBridge 正在运行且端口未被占用'
    : lastError?.message?.includes('Failed to fetch')
      ? '无法连接，可能原因：1) XFAgentBridge 未启动 2) 浏览器阻止了本地网络访问（检查浏览器 Private Network Access 设置）3) 端口被占用'
      : lastError?.message || '未知错误'
  throw new Error(`本机 XFAgentBridge 未运行（${baseUrl}）：${hint}`)
}

export async function executeLocalDeskTask(agentType, taskId, params) {
  const baseUrl = getBridgeBaseUrl()
  await checkLocalDeskBridge()

  const payload = {
    request_id: buildRequestId(),
    agent_type: agentType,
    task_id: taskId,
    params,
    source: {
      origin: window.location.origin,
      user_id: getExternalUserId(),
      display_name: getExternalDisplayName(),
    },
    submitted_at: new Date().toISOString(),
  }

  return fetchJsonWithTimeout(`${baseUrl}/api/v1/tasks/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, 30000)
}
