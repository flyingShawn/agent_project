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

export async function listOpsReports(agentType, { limit = 20, unreadOnly = false } = {}) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/ops/reports?limit=${limit}&unread_only=${unreadOnly}`)
  return parseJsonResponse(response)
}

export async function getLatestOpsReport(agentType) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/ops/reports/latest`)
  return parseJsonResponse(response)
}

export async function getOpsReport(agentType, reportId) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/ops/reports/${reportId}`)
  return parseJsonResponse(response)
}

export async function markOpsReportRead(agentType, reportId) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/ops/reports/${reportId}/read`, {
    method: 'PUT',
  })
  return parseJsonResponse(response)
}

export async function runOpsReportNow(agentType) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/ops/reports/run`, {
    method: 'POST',
  })
  return parseJsonResponse(response)
}
