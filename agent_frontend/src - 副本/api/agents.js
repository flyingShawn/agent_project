const API_BASE = '/api/v1'

let _agentsCache = null

export async function fetchAgents() {
  if (_agentsCache) return _agentsCache
  try {
    const response = await fetch(`${API_BASE}/agents`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const data = await response.json()
    _agentsCache = data
    return data
  } catch (e) {
    console.error('[Agents API] 获取智能体列表失败:', e)
    return { agents: [], default_agent_type: '' }
  }
}

export function clearAgentsCache() {
  _agentsCache = null
}
