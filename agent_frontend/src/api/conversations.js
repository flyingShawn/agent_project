const API_BASE = '/api/v1'

export async function getConversations(userId = 'admin', limit = 50, offset = 0) {
  const response = await fetch(
    `${API_BASE}/conversations?user_id=${encodeURIComponent(userId)}&limit=${limit}&offset=${offset}`
  )
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function getConversation(id) {
  const response = await fetch(`${API_BASE}/conversations/${id}`)
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function createConversation(userId = 'admin') {
  const response = await fetch(`${API_BASE}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function updateConversationTitle(id, title) {
  const response = await fetch(`${API_BASE}/conversations/${id}/title`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}

export async function deleteConversation(id) {
  const response = await fetch(`${API_BASE}/conversations/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return response.json()
}
