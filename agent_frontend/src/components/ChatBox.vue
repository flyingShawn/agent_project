<script setup>
import { ref, nextTick, onUnmounted, computed } from 'vue'
import MessageBubble from './MessageBubble.vue'
import ImageUploader from './ImageUploader.vue'
import { sendChatMessage } from '../api/chat'
import config from '../config'

const props = defineProps({
  userName: {
    type: String,
    default: 'admin',
  },
  showSidebar: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close-sidebar', 'new-session'])

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
  emit('close-sidebar')
}

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
      await fetch('/api/v1/chat/end', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: currentSessionId.value,
        }),
      })
    } catch (error) {
      console.error('[前端 ChatBox] 结束会话失败:', error)
    }
  }
  currentSessionId.value = null
  messages.value = []
}

const sendMessage = async (overrideText) => {
  const text = (overrideText || inputText.value).trim()

  if (!text && pendingImages.value.length === 0) return
  if (isLoading.value) return

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
    timestamp: new Date().toISOString(),
    isStreaming: true,
  }
  messages.value.push(assistantMessage)
  await scrollToBottom()

  try {
    const history = messages.value
      .filter((m) => m.id !== assistantMessageId)
      .map((m) => ({
        role: m.role,
        content: m.content,
      }))

    await sendChatMessage({
      question: text,
      history: history,
      images_base64: imagesToSend.map((img) => img.base64),
      lognum: props.userName,
      mode: 'auto',
      session_id: currentSessionId.value,
      onEvent: (event, data) => {
        const msgIndex = messages.value.findIndex(m => m.id === assistantMessageId)
        if (msgIndex === -1) return

        if (event === 'start') {
          messages.value[msgIndex].intent = data.intent
          if (data.session_id) {
            currentSessionId.value = data.session_id
          }
        } else if (event === 'delta') {
          messages.value[msgIndex].content += data
          scrollToBottom()
        } else if (event === 'done') {
          messages.value[msgIndex].isStreaming = false
          messages.value[msgIndex].route = data.route
          if (data.session_id) {
            currentSessionId.value = data.session_id
          }
        } else if (event === 'error') {
          messages.value[msgIndex].isStreaming = false
          messages.value[msgIndex].content = `错误: ${data.error}`
          messages.value[msgIndex].isError = true
        }
      },
    })
  } catch (error) {
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

onUnmounted(() => {
  pendingImages.value = []
  if (currentSessionId.value) {
    fetch('/api/v1/chat/end', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
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
  <div class="h-full flex flex-col relative">
    <Transition name="fade">
      <div
        v-if="showSidebar"
        class="fixed inset-0 bg-black/30 z-20"
        @click="emit('close-sidebar')"
      ></div>
    </Transition>

    <Transition name="slide">
      <div
        v-if="showSidebar"
        class="fixed left-0 top-0 bottom-0 w-72 bg-white shadow-xl z-30 flex flex-col"
      >
        <div class="p-4 pb-2">
          <h2 class="text-base font-semibold text-text-primary">{{ config.appName }}</h2>
        </div>
        <div class="px-3 pb-3">
          <button
            @click="handleNewSession"
            class="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-primary-500 hover:bg-primary-50 rounded-lg transition-colors cursor-pointer border border-primary-200 bg-primary-50/50"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v16m8-8H4" />
            </svg>
            开启新会话
          </button>
        </div>
        <div class="px-4 pb-2">
          <p class="text-xs text-text-tertiary font-medium">历史会话</p>
        </div>
        <div class="flex-1 overflow-y-auto px-3 pb-3">
          <div class="text-center py-8 text-text-tertiary text-sm">
            <svg class="w-10 h-10 mx-auto mb-2 text-text-tertiary/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            暂无历史会话
          </div>
        </div>
        <div class="p-3 border-t border-[#e8ecf2]">
          <button
            @click="emit('close-sidebar')"
            class="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded-lg transition-colors cursor-pointer"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            收起侧栏
          </button>
        </div>
      </div>
    </Transition>

    <div
      ref="messagesContainer"
      class="flex-1 overflow-y-auto"
      @paste="handlePaste"
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
          :placeholder="config.inputPlaceholder"
          rows="1"
          class="flex-1 resize-none bg-transparent px-1 py-1 text-sm focus:outline-none placeholder:text-text-tertiary"
          :disabled="isLoading"
        ></textarea>

        <button
          @click="sendMessage()"
          :disabled="isLoading || (!inputText.trim() && pendingImages.length === 0)"
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
          v-if="currentSessionId"
          @click="resetSession"
          :disabled="isLoading"
          class="hover:text-text-secondary transition-colors cursor-pointer"
        >
          新对话
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
}
</style>
