import { fetchWithExternalAuth } from '../utils/externalIdentity'

const API_BASE = '/api/v1/ops'

async function parseJsonResponse(response) {
  if (!response.ok) {
    let detail = `HTTP error! status: ${response.status}`
    try {
      const payload = await response.json()
      detail = payload.detail || detail
    } catch (_) {
      // ignore
    }
    throw new Error(detail)
  }
  return response.json()
}

export async function listOpsReports({ limit = 20, unreadOnly = false } = {}) {
  const response = await fetchWithExternalAuth(`${API_BASE}/reports?limit=${limit}&unread_only=${unreadOnly}`)
  return parseJsonResponse(response)
}

export async function getLatestOpsReport() {
  const response = await fetchWithExternalAuth(`${API_BASE}/reports/latest`)
  return parseJsonResponse(response)
}

export async function getOpsReport(reportId) {
  const response = await fetchWithExternalAuth(`${API_BASE}/reports/${reportId}`)
  return parseJsonResponse(response)
}

export async function markOpsReportRead(reportId) {
  const response = await fetchWithExternalAuth(`${API_BASE}/reports/${reportId}/read`, {
    method: 'PUT',
  })
  return parseJsonResponse(response)
}

export async function runOpsReportNow() {
  const response = await fetchWithExternalAuth(`${API_BASE}/reports/run`, {
    method: 'POST',
  })
  return parseJsonResponse(response)
}
