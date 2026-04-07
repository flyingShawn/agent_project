<script setup>
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import MessageBubble from './MessageBubble.vue'
import ImageUploader from './ImageUploader.vue'
import { sendChatMessage } from '../api/chat'

const props = defineProps({
  userName: {
    type: String,
    default: 'admin',
  },
})

const messages = ref([])
const inputText = ref('')
const isLoading = ref(false)
const pendingImages = ref([])
const messagesContainer = ref(null)

const handlePaste = (event) => {
  const items = event.clipboardData?.items
  if (!items) return

  for (const item of items) {
    if (item.type.startsWith('image/')) {
      event.preventDefault()
      const file = item.getAsFile()
      if (file) {
        addImageFile(file)
      }
      break
    }
  }
}

const addImageFile = (file) => {
  const reader = new FileReader()
  reader.onload = (e) => {
    const base64 = e.target.result.split(',')[1]
    pendingImages.value.push({
      id: Date.now(),
      preview: e.target.result,
      base64: base64,
      name: file.name,
    })
  }
  reader.readAsDataURL(file)
}

const removePendingImage = (id) => {
  pendingImages.value = pendingImages.value.filter((img) => img.id !== id)
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const sendMessage = async () => {
    console.log('[前端 ChatBox] sendMessage 被调用')
    const text = inputText.value.trim()
    console.log('[前端 ChatBox] 用户输入:', text)
    
    if (!text && pendingImages.value.length === 0) {
      console.log('[前端 ChatBox] 输入为空，返回')
      return
    }
    if (isLoading.value) {
      console.log('[前端 ChatBox] 正在加载中，返回')
      return
    }

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: text,
      images: pendingImages.value.map((img) => ({
        preview: img.preview,
        base64: img.base64,
      })),
      timestamp: new Date().toISOString(),
    }

    console.log('[前端 ChatBox] 添加用户消息到聊天记录')
    messages.value.push(userMessage)
    inputText.value = ''
    const imagesToSend = [...pendingImages.value]
    pendingImages.value = []
    isLoading.value = true

    await scrollToBottom()

    const assistantMessageIndex = messages.value.length
    const assistantMessageId = Date.now() + 1
    
    const assistantMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      intent: null,
      timestamp: new Date().toISOString(),
      isStreaming: true,
    }
    console.log('[前端 ChatBox] 添加助手消息占位符')
    messages.value.push(assistantMessage)
    await scrollToBottom()

    try {
      const history = messages.value
        .filter((m) => m.id !== assistantMessageId)
        .map((m) => ({
          role: m.role,
          content: m.content,
        }))

      console.log('[前端 ChatBox] 准备调用API')

      await sendChatMessage({
        question: text,
        history: history,
        images_base64: imagesToSend.map((img) => img.base64),
        lognum: props.userName,
        mode: 'auto',
        onEvent: (event, data) => {
          console.log('[前端 ChatBox] 收到事件:', { event, data })
          
          const msgIndex = messages.value.findIndex(m => m.id === assistantMessageId)
          if (msgIndex === -1) return
          
          if (event === 'start') {
            messages.value[msgIndex].intent = data.intent
          } else if (event === 'delta') {
            messages.value[msgIndex].content += data
            scrollToBottom()
          } else if (event === 'done') {
            messages.value[msgIndex].isStreaming = false
            messages.value[msgIndex].route = data.route
          } else if (event === 'error') {
            messages.value[msgIndex].isStreaming = false
            messages.value[msgIndex].content = `错误: ${data.error}`
            messages.value[msgIndex].isError = true
          }
        },
      })
      console.log('[前端 ChatBox] API调用完成')
    } catch (error) {
      console.error('[前端 ChatBox] 发生错误:', error)
      const msgIndex = messages.value.findIndex(m => m.id === assistantMessageId)
      if (msgIndex !== -1) {
        messages.value[msgIndex].isStreaming = false
        messages.value[msgIndex].content = `请求失败: ${error.message}`
        messages.value[msgIndex].isError = true
      }
    } finally {
      isLoading.value = false
      await scrollToBottom()
    }
  }

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

onMounted(() => {
  messages.value.push({
    id: Date.now(),
    role: 'assistant',
    content: '你好！我是桌管系统 AI 助手。我可以帮助你：\n\n- 查询设备资产信息\n- 了解策略配置方法\n- 排查常见问题\n- 分析数据统计\n\n请问有什么可以帮你的？',
    timestamp: new Date().toISOString(),
  })
})

onUnmounted(() => {
  pendingImages.value = []
})
</script>

<template>
  <div class="h-full flex flex-col">
    <div
      ref="messagesContainer"
      class="flex-1 overflow-y-auto px-4 py-6 space-y-4"
      @paste="handlePaste"
    >
      <TransitionGroup name="slide-up">
        <MessageBubble
          v-for="message in messages"
          :key="message.id"
          :message="message"
        />
      </TransitionGroup>
      
      <div v-if="isLoading" class="flex justify-start">
        <div class="bg-white rounded-2xl px-4 py-3 shadow-sm border border-gray-100">
          <div class="flex items-center space-x-2 text-gray-500">
            <div class="flex space-x-1">
              <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
              <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
              <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
            </div>
            <span class="text-sm">思考中...</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="pendingImages.length > 0" class="px-4 py-2 border-t border-gray-100 bg-white">
      <div class="flex flex-wrap gap-2">
        <div
          v-for="img in pendingImages"
          :key="img.id"
          class="relative group"
        >
          <img
            :src="img.preview"
            :alt="img.name"
            class="w-16 h-16 object-cover rounded-lg border border-gray-200"
          />
          <button
            @click="removePendingImage(img.id)"
            class="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full text-xs opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
          >
            ×
          </button>
        </div>
      </div>
    </div>

    <div class="border-t border-gray-200 bg-white p-4">
      <div class="flex items-end space-x-3">
        <ImageUploader @select="addImageFile" />
        
        <div class="flex-1 relative">
          <textarea
            v-model="inputText"
            @keydown="handleKeydown"
            placeholder="输入问题，按 Enter 发送..."
            rows="1"
            class="w-full resize-none rounded-xl border border-gray-300 px-4 py-3 pr-12 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
            :disabled="isLoading"
          ></textarea>
        </div>
        
        <button
          @click="sendMessage"
          :disabled="isLoading || (!inputText.trim() && pendingImages.length === 0)"
          class="px-5 py-3 bg-primary-500 text-white rounded-xl hover:bg-primary-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center space-x-2"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
          </svg>
        </button>
      </div>
      
      <div class="flex items-center justify-between mt-2 text-xs text-gray-400">
        <span>支持粘贴截图 | Shift+Enter 换行</span>
      </div>
    </div>
  </div>
</template>
