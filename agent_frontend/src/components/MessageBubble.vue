<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

marked.setOptions({
  highlight: function (code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (e) {
        console.error(e)
      }
    }
    return hljs.highlightAuto(code).value
  },
  breaks: true,
  gfm: true,
})

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  const rawHtml = marked.parse(props.message.content)
  return DOMPurify.sanitize(rawHtml)
})

const isUser = computed(() => props.message.role === 'user')

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getIntentLabel = (intent) => {
  const labels = {
    sql: '数据查询',
    rag: '知识问答',
  }
  return labels[intent] || ''
}
</script>

<template>
  <div
    class="flex"
    :class="isUser ? 'justify-end' : 'justify-start'"
  >
    <div
      class="max-w-[85%] md:max-w-[70%]"
      :class="isUser ? 'order-1' : 'order-2'"
    >
      <div v-if="message.images && message.images.length > 0" class="mb-2 flex flex-wrap gap-2">
        <img
          v-for="(img, index) in message.images"
          :key="index"
          :src="img.preview"
          class="max-w-[200px] rounded-lg border border-gray-200 shadow-sm"
          alt="上传的图片"
        />
      </div>
      
      <div
        class="rounded-2xl px-4 py-3 shadow-sm"
        :class="[
          isUser
            ? 'bg-primary-500 text-white rounded-br-md'
            : 'bg-white border border-gray-100 rounded-bl-md',
          message.isError ? 'bg-red-50 border-red-200' : '',
        ]"
      >
        <div
          v-if="!isUser && message.intent"
          class="flex items-center space-x-2 mb-2 pb-2 border-b border-gray-100"
        >
          <span
            class="text-xs px-2 py-0.5 rounded-full"
            :class="message.intent === 'sql' ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'"
          >
            {{ getIntentLabel(message.intent) }}
          </span>
        </div>
        
        <div
          class="message-content prose prose-sm max-w-none"
          :class="[
            isUser ? 'prose-invert text-white' : 'text-gray-800',
            message.isStreaming ? 'typing-cursor' : '',
          ]"
          v-html="renderedContent"
        ></div>
      </div>
      
      <div
        class="text-xs mt-1 px-1"
        :class="isUser ? 'text-right text-gray-400' : 'text-left text-gray-400'"
      >
        {{ formatTime(message.timestamp) }}
      </div>
    </div>
  </div>
</template>

<style>
.message-content pre {
  margin: 0.5rem 0;
  border-radius: 0.5rem;
  overflow-x: auto;
}

.message-content pre code {
  font-size: 0.875rem;
  line-height: 1.5;
}

.message-content code {
  font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
}

.message-content table {
  border-collapse: collapse;
  width: 100%;
  display: table;
}

.message-content .message-content-inner {
  overflow-x: auto;
}

.message-content p:first-child {
  margin-top: 0;
}

.message-content p:last-child {
  margin-bottom: 0;
}
</style>
