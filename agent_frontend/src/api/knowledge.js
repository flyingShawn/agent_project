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

export async function fetchKnowledgeFiles(agentType, kbType) {
  const params = new URLSearchParams({ kb_type: kbType })
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files?${params}`)
  return parseJsonResponse(response)
}

export async function createKnowledgeFile(agentType, kbType, name, editorName) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kb_type: kbType, name, editor_name: editorName }),
  })
  return parseJsonResponse(response)
}

export async function renameKnowledgeFile(agentType, kbType, filename, newName, editorName) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files/${encodeURIComponent(filename)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kb_type: kbType, new_name: newName, editor_name: editorName }),
  })
  return parseJsonResponse(response)
}

export async function fetchKnowledgeEntries(agentType, kbType, filename) {
  const params = new URLSearchParams({ kb_type: kbType })
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files/${encodeURIComponent(filename)}/entries?${params}`)
  return parseJsonResponse(response)
}

export async function addKnowledgeEntry(agentType, payload) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files/${encodeURIComponent(payload.filename)}/entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kb_type: payload.kbType,
      title: payload.title,
      scenario: payload.scenario,
      key_tables: payload.keyTables || '',
      sql_code: payload.sqlCode || '',
      answer: payload.answer || '',
      editor_name: payload.editorName || '',
    }),
  })
  return parseJsonResponse(response)
}

export async function updateKnowledgeEntry(agentType, payload) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files/${encodeURIComponent(payload.filename)}/entries/${payload.entryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kb_type: payload.kbType,
      title: payload.title,
      scenario: payload.scenario,
      key_tables: payload.keyTables || '',
      sql_code: payload.sqlCode || '',
      answer: payload.answer || '',
      editor_name: payload.editorName || '',
    }),
  })
  return parseJsonResponse(response)
}

export async function deleteKnowledgeEntry(agentType, payload) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files/${encodeURIComponent(payload.filename)}/entries/${payload.entryId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kb_type: payload.kbType,
      editor_name: payload.editorName || '',
    }),
  })
  return parseJsonResponse(response)
}

export async function deleteKnowledgeFile(agentType, payload) {
  const response = await fetchWithExternalAuth(`${API_BASE}/${agentType}/knowledge/files/${encodeURIComponent(payload.filename)}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kb_type: payload.kbType,
      editor_name: payload.editorName || '',
    }),
  })
  return parseJsonResponse(response)
}
