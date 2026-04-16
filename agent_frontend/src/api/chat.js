const API_BASE = '/api/v1'

export async function sendChatMessage({
  question,
  history = [],
  images_base64 = null,
  lognum = 'admin',
  mode = 'auto',
  session_id = null,
  onEvent,
}) {
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
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = null
      let currentData = null

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
    }
  } catch (error) {
    console.error('[Chat API] Error:', error)
    throw error
  }
}
