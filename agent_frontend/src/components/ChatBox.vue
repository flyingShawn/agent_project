<script setup>
import { ref, nextTick, onUnmounted, computed } from 'vue'
import MessageBubble from './MessageBubble.vue'
import ImageUploader from './ImageUploader.vue'
import { sendChatMessage, abortCurrentRequest } from '../api/chat'
import { useConversations } from '../composables/useConversations'
import config from '../config'
import { appendExternalAuthParams, fetchWithExternalAuth } from '../utils/externalIdentity'

const props = defineProps({
  userId: {
    type: String,
    default: 'admin',
  },
})

const emit = defineEmits(['conversation-created', 'conversation-updated'])

const { currentConversationId, updateConversationInList, loadConversations } = useConversations()

const messages = ref([])
const inputText = ref('')
const isLoading = ref(false)
const pendingImages = ref([])
const messagesContainer = ref(null)
const currentSessionId = ref(null)
const textareaRef = ref(null)

const hasMessages = computed(() => messages.value.length > 0)

const handleQuickOption = (label) => {
  inputText.value = label
  sendMessage()
}

const handleNewSession = () => {
  resetSession()
}

const loadConversation = (conversationData) => {
  if (currentSessionId.value) {
    fetchWithExternalAuth('/api/v1/chat/end', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId.value }),
    }).catch(() => {})
  }
  currentSessionId.value = null
  currentConversationId.value = conversationData.id
  const rawMessages = conversationData.messages || []
  messages.value = rawMessages.map((m) => {
    let charts = []
    if (m.charts) {
      try {
        charts = typeof m.charts === 'string' ? JSON.parse(m.charts) : m.charts
        if (!Array.isArray(charts)) charts = []
      } catch {
        charts = []
      }
    }
    return {
      id: Date.now() + Math.random(),
      role: m.role,
      content: m.content,
      intent: m.intent,
      charts,
      timestamp: new Date(m.created_at * 1000).toISOString(),
      isStreaming: false,
    }
  })
  if (rawMessages.length > 0 && rawMessages[rawMessages.length - 1].role === 'user') {
    messages.value.push({
      id: Date.now() + Math.random(),
      role: 'assistant',
      content: '（回复被中断，请重新发送消息）',
      intent: null,
      charts: [],
      timestamp: new Date().toISOString(),
      isStreaming: false,
      isInterrupted: true,
    })
  }
  nextTick(() => scrollToBottom())
}

defineExpose({ handleNewSession, loadConversation })

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

const autoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 150) + 'px'
  }
}

const resetSession = async () => {
  if (currentSessionId.value) {
    try {
      await fetchWithExternalAuth('/api/v1/chat/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId.value }),
      })
    } catch (error) {
      console.error('[前端 ChatBox] 结束会话失败:', error)
    }
  }
  currentSessionId.value = null
  currentConversationId.value = null
  messages.value = []
}

const stopGeneration = () => {
  abortCurrentRequest()
}

const buildExportLinkText = (data) => {
  if (!data?.download_url || !data?.filename) return ''
  const downloadUrl = appendExternalAuthParams(data.download_url)

  if (data.overflow_capped) {
    const exportCount = Number(data.export_row_count || 5000)
    return `\n\n数据量过大，当前已导出前${exportCount}条，详情可查看具体表格：[${data.filename}](${downloadUrl})`
  }

  if (Number(data.row_count || 0) > 20) {
    return `\n\n当前查询数量过多，详情可查看具体表格：[${data.filename}](${downloadUrl})`
  }

  return `\n\n以下是表格数据，可进行下载：[${data.filename}](${downloadUrl})`
}

const sendMessage = async (overrideText) => {
  const text = (overrideText || inputText.value).trim()

  if (!text && pendingImages.value.length === 0) return

  if (isLoading.value) {
    stopGeneration()
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

  messages.value.push(userMessage)
  inputText.value = ''
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
  const imagesToSend = [...pendingImages.value]
  pendingImages.value = []
  isLoading.value = true

  await scrollToBottom()

  const assistantMessageId = Date.now() + 1

  const assistantMessage = {
    id: assistantMessageId,
    role: 'assistant',
    content: '',
    intent: null,
    charts: [],
    timestamp: new Date().toISOString(),
    isStreaming: true,
  }
  messages.value.push(assistantMessage)
  await scrollToBottom()

  try {
    await sendChatMessage({
      question: text,
      history: [],
      images_base64: imagesToSend.map((img) => img.base64),
      lognum: props.userId,
      mode: 'auto',
      session_id: currentSessionId.value,
      conversation_id: currentConversationId.value,
      onEvent: (event, data) => {
        const msgIndex = messages.value.findIndex(m => m.id === assistantMessageId)
        if (msgIndex === -1) return

        const msg = messages.value[msgIndex]

        if (event === 'start') {
          msg.intent = data.intent
          if (data.session_id) {
            currentSessionId.value = data.session_id
          }
          if (data.conversation_id && !currentConversationId.value) {
            currentConversationId.value = data.conversation_id
            emit('conversation-created', data.conversation_id)
          }
        } else if (event === 'status') {
          msg.content = data
          scrollToBottom()
        } else if (event === 'replace') {
          msg.content = ''
        } else if (event === 'delta') {
          msg.content = msg.content + data
          scrollToBottom()
        } else if (event === 'export') {
          if (data.download_url && data.filename) {
            msg.content = msg.content + buildExportLinkText(data)
            scrollToBottom()
          }
        } else if (event === 'chart') {
          if (data && data.echarts_option) {
            msg.charts = [...(msg.charts || []), data]
            scrollToBottom()
          }
        } else if (event === 'done') {
          msg.isStreaming = false
          msg.route = data.route
          if (data.session_id) {
            currentSessionId.value = data.session_id
          }
          if (data.conversation_id) {
            currentConversationId.value = data.conversation_id
          }
          emit('conversation-updated')
        } else if (event === 'error') {
          msg.isStreaming = false
          msg.content = `错误: ${data.error}`
          msg.isError = true
        }
      },
    })
  } catch (error) {
    const msgIndex = messages.value.findIndex(m => m.id === assistantMessageId)
    if (msgIndex !== -1) {
      if (error.name === 'AbortError') {
        messages.value[msgIndex].isStreaming = false
        if (!messages.value[msgIndex].content) {
          messages.value[msgIndex].content = '已停止生成'
        }
        messages.value[msgIndex].isStopped = true
      } else {
        messages.value[msgIndex].isStreaming = false
        messages.value[msgIndex].content = `请求失败: ${error.message}`
        messages.value[msgIndex].isError = true
      }
    }
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (isLoading.value) return
    sendMessage()
  }
}

onUnmounted(() => {
  pendingImages.value = []
  if (currentSessionId.value) {
    fetchWithExternalAuth('/api/v1/chat/end', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId.value,
      }),
    }).catch(error => {
      console.error('[前端 ChatBox] 结束会话失败:', error)
    })
  }
})
</script>

<template>
  <div class="h-full flex flex-col relative" @paste="handlePaste">
    <div
      ref="messagesContainer"
      class="flex-1 overflow-y-auto no-scrollbar"
    >
      <div v-if="!hasMessages" class="h-full flex flex-col items-center justify-center px-6 pb-24">
        <div class="text-center mb-8">
          <h2 class="text-2xl font-semibold text-text-primary mb-2">{{ config.welcomeText }}</h2>
        </div>

        <div class="flex flex-wrap justify-center gap-2.5 max-w-lg">
          <button
            v-for="option in config.quickOptions"
            :key="option"
            @click="handleQuickOption(option)"
            class="quick-option-card bg-white border border-[#e8ecf2] rounded-full px-4 py-2 text-sm text-text-secondary hover:text-primary-500 hover:border-primary-300 transition-all cursor-pointer"
          >
            {{ option }}
          </button>
        </div>
      </div>

      <div v-else class="px-4 py-6 space-y-5">
        <TransitionGroup name="slide-up">
          <MessageBubble
            v-for="message in messages"
            :key="message.id"
            :message="message"
          />
        </TransitionGroup>

        <div v-if="isLoading && messages[messages.length - 1]?.content === ''" class="flex justify-start">
          <div class="bg-white rounded-bubble rounded-bl-sm px-4 py-3 shadow-card border border-[#e8ecf2]">
            <div class="flex items-center space-x-2 text-text-tertiary">
              <div class="flex space-x-1">
                <div class="w-1.5 h-1.5 bg-primary-400 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
                <div class="w-1.5 h-1.5 bg-primary-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
                <div class="w-1.5 h-1.5 bg-primary-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
              </div>
              <span class="text-xs">思考中...</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="bg-transparent px-4 pb-4 pt-2">
      <div v-if="pendingImages.length > 0" class="mb-3 flex flex-wrap gap-2">
        <div
          v-for="img in pendingImages"
          :key="img.id"
          class="relative group"
        >
          <img
            :src="img.preview"
            :alt="img.name"
            class="w-14 h-14 object-cover rounded-lg border border-[#e8ecf2]"
          />
          <button
            @click="removePendingImage(img.id)"
            class="absolute -top-1.5 -right-1.5 w-4.5 h-4.5 bg-red-500 text-white rounded-full text-[10px] opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-pointer"
          >
            ×
          </button>
        </div>
      </div>

      <div class="chat-input-box flex items-end gap-2 bg-white rounded-2xl border border-[#d9d9e3] px-4 py-3 shadow-sm focus-within:border-primary-400 focus-within:shadow-md transition-all">
        <ImageUploader @select="addImageFile" />

        <textarea
          ref="textareaRef"
          v-model="inputText"
          @keydown="handleKeydown"
          @input="autoResize"
          :placeholder="isLoading ? '回复中，输入内容等待发送...' : config.inputPlaceholder"
          rows="1"
          class="flex-1 resize-none bg-transparent px-1 py-1 text-sm focus:outline-none placeholder:text-text-tertiary"
        ></textarea>

        <button
          v-if="isLoading"
          @click="stopGeneration"
          class="flex-shrink-0 w-8 h-8 bg-red-500 text-white rounded-full hover:bg-red-600 transition-all flex items-center justify-center cursor-pointer"
          title="停止生成"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="6" width="12" height="12" rx="1" />
          </svg>
        </button>
        <button
          v-else
          @click="sendMessage()"
          :disabled="!inputText.trim() && pendingImages.length === 0"
          class="flex-shrink-0 w-8 h-8 bg-primary-500 text-white rounded-full hover:bg-primary-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-all flex items-center justify-center cursor-pointer"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      <div class="flex items-center justify-between mt-2 text-[11px] text-text-tertiary px-1">
        <span>支持粘贴截图 · Shift+Enter 换行</span>
        <button
          v-if="currentSessionId || currentConversationId"
          @click="resetSession"
          class="hover:text-text-secondary transition-colors cursor-pointer"
        >
          新对话
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
