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
  console.log('[前端 API] 开始发送聊天请求')
  console.log('[前端 API] 请求参数:', { question, history, lognum, mode, session_id })
  
  try {
    console.log('[前端 API] 发送请求到:', `${API_BASE}/chat`)
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

    console.log('[前端 API] 收到响应，状态码:', response.status)

    if (!response.ok) {
      console.error('[前端 API] HTTP错误! 状态:', response.status)
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    console.log('[前端 API] 开始读取SSE流')

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        console.log('[前端 API] SSE流读取完成')
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = null
      let currentData = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
          console.log('[前端 API] 收到event:', currentEvent)
        } else if (line.startsWith('data: ')) {
          const dataContent = line.slice(6)
          if (currentData === '') {
            currentData = dataContent
          } else {
            currentData = currentData + '\n' + dataContent
          }
        } else if (line === '' && currentEvent && currentData !== '') {
          try {
            const parsedData = JSON.parse(currentData)
            console.log('[前端 API] 解析data成功:', { event: currentEvent, data: parsedData })
            onEvent(currentEvent, parsedData)
          } catch (e) {
            console.log('[前端 API] 解析data失败，直接传递:', { event: currentEvent, data: currentData })
            onEvent(currentEvent, currentData)
          }
          currentEvent = null
          currentData = ''
        }
      }
    }
  } catch (error) {
    console.error('[前端 API] 发生错误:', error)
    throw error
  }
}


