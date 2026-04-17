const API_BASE = '/api/v1'

let currentAbortController = null

export function abortCurrentRequest() {
  if (currentAbortController) {
    currentAbortController.abort()
    currentAbortController = null
  }
}

export async function sendChatMessage({
  question,
  history = [],
  images_base64 = null,
  lognum = 'admin',
  mode = 'auto',
  session_id = null,
  conversation_id = null,
  onEvent,
}) {
  const controller = new AbortController()
  currentAbortController = controller

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        history,
        images_base64,
        lognum,
        mode,
        session_id,
        conversation_id,
      }),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    const processLines = (lines, currentEvent, currentData) => {
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const dataContent = line.slice(6)
          if (currentData === null) {
            currentData = dataContent
          } else {
            currentData = currentData + '\n' + dataContent
          }
        } else if (line === '' && currentEvent && currentData !== null) {
          try {
            const parsedData = JSON.parse(currentData)
            onEvent(currentEvent, parsedData)
          } catch (e) {
            onEvent(currentEvent, currentData)
          }
          currentEvent = null
          currentData = null
        }
      }
      return { currentEvent, currentData }
    }

    let pendingEvent = null
    let pendingData = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      const result = processLines(lines, pendingEvent, pendingData)
      pendingEvent = result.currentEvent
      pendingData = result.currentData
    }

    if (buffer.trim() || pendingEvent) {
      const finalLines = buffer.split('\n')
      processLines(finalLines, pendingEvent, pendingData)
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('[Chat API] 请求已被用户中断')
      throw new DOMException('请求已被用户中断', 'AbortError')
    }
    console.error('[Chat API] Error:', error)
    throw error
  } finally {
    if (currentAbortController === controller) {
      currentAbortController = null
    }
  }
}
