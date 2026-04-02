const API_BASE = '/api/v1'

export async function sendChatMessage({
  question,
  history = [],
  images_base64 = null,
  lognum = 'admin',
  mode = 'auto',
  onEvent,
}) {
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
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = null
    let currentData = ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
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
          onEvent(currentEvent, parsedData)
        } catch (e) {
          onEvent(currentEvent, currentData)
        }
        currentEvent = null
        currentData = ''
      }
    }
  }
}

export async function sendChatMessageMock({ question, onEvent }) {
  await new Promise((resolve) => setTimeout(resolve, 300))
  
  const isSqlIntent = question.includes('多少') || 
                      question.includes('统计') || 
                      question.includes('查询') ||
                      question.includes('设备') ||
                      question.includes('在线')
  
  const intent = isSqlIntent ? 'sql' : 'rag'
  onEvent('start', { intent })
  
  await new Promise((resolve) => setTimeout(resolve, 200))
  
  if (intent === 'sql') {
    const sqlResponse = `查询结果如下：

\`\`\`json
[
  {
    "IP": "192.168.1.10",
    "设备名称": "研发部-张三-PC",
    "状态": "在线",
    "所属部门": "研发部",
    "最后上线": "2024-01-15 09:30:00"
  },
  {
    "IP": "192.168.1.11",
    "设备名称": "研发部-李四-PC",
    "状态": "离线",
    "所属部门": "研发部",
    "最后上线": "2024-01-14 18:45:00"
  }
]
\`\`\`

共查询到 **2** 台设备，其中 **1** 台在线，**1** 台离线。`
    
    for (const char of sqlResponse) {
      await new Promise((resolve) => setTimeout(resolve, 15))
      onEvent('delta', char)
    }
  } else {
    const ragResponse = `根据操作手册，水印策略设置步骤如下：

## 设置步骤

1. 进入【策略管理】模块
2. 点击左侧菜单【水印策略】
3. 点击【新建策略】按钮
4. 配置水印参数

## 参数说明

| 参数名称 | 说明 | 取值范围 |
|---------|------|---------|
| 透明度 | 水印透明程度 | 0-100 |
| 字体大小 | 水印文字大小 | 12-24px |
| 显示位置 | 水印显示位置 | 左上/右上/左下/右下 |
| 显示内容 | 水印包含的信息 | 用户名/IP/时间 |

> **注意**：水印策略生效需要客户端重启后方可生效。`
    
    for (const char of ragResponse) {
      await new Promise((resolve) => setTimeout(resolve, 12))
      onEvent('delta', char)
    }
  }
  
  await new Promise((resolve) => setTimeout(resolve, 100))
  onEvent('done', { route: intent, meta: {} })
}
