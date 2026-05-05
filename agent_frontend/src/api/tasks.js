import { fetchWithExternalAuth } from '../utils/externalIdentity'

const API_BASE = '/api/v1'

async function parseJsonResponse(response) {
  if (!response.ok) {
    let detail = `HTTP error! status: ${response.status}`
    try {
      const payload = await response.json()
      detail = payload.detail || detail
    } catch (_) {
    }
    throw new Error(detail)
  }
  return response.json()
}

export async function fetchTasks(agentType) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/tasks`)
  return parseJsonResponse(response)
}

export async function fetchTaskSchema(agentType, taskId) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/tasks/${taskId}/schema`)
  return parseJsonResponse(response)
}

export async function validateTaskStep(agentType, taskId, stepId, params) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/tasks/${taskId}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ step_id: stepId, params }),
  })
  return parseJsonResponse(response)
}

export async function executeTask(agentType, taskId, params) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/tasks/${taskId}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ params }),
  })
  return parseJsonResponse(response)
}

export async function fetchTaskOptions(agentType, optionType, keyword = '') {
  const params = keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/tasks/options/${optionType}${params}`)
  return parseJsonResponse(response)
}
