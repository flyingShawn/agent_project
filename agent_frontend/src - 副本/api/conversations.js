import { fetchWithExternalAuth } from '../utils/externalIdentity'

const API_BASE = '/api/v1'

export async function getConversations(agentType, userId = 'admin', limit = 50, offset = 0) {
  const response = await fetchWithExternalAuth(
    `${API_BASE}/${agentType}/conversations?user_id=${encodeURIComponent(userId)}&limit=${limit}&offset=${offset}`
  )
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function getConversation(agentType, id) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/conversations/${id}`)
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function createConversation(agentType, userId = 'admin') {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function updateConversationTitle(agentType, id, title) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/conversations/${id}/title`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function deleteConversation(agentType, id) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/conversations/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}
