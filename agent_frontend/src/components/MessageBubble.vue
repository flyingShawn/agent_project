<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
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

const renderedHtml = ref('')
let renderRafId = null

const rawContent = computed(() => props.message.content || '')
const isStreaming = computed(() => props.message.isStreaming)

const renderMarkdown = (content) => {
  if (!content) {
    renderedHtml.value = ''
    return
  }
  const rawHtml = marked.parse(content)
  renderedHtml.value = DOMPurify.sanitize(rawHtml)
}

watch(
  [rawContent, isStreaming],
  ([content, streaming]) => {
    if (renderRafId) {
      cancelAnimationFrame(renderRafId)
      renderRafId = null
    }

    if (!streaming) {
      renderMarkdown(content)
      return
    }

    renderRafId = requestAnimationFrame(() => {
      renderRafId = null
      renderMarkdown(rawContent.value)
    })
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }
})

const isUser = computed(() => props.message.role === 'user')

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
      class="max-w-[85%] sm:max-w-[75%]"
    >
      <div v-if="message.images && message.images.length > 0" class="mb-2 flex flex-wrap gap-2" :class="isUser ? 'justify-end' : 'justify-start'">
        <img
          v-for="(img, index) in message.images"
          :key="index"
          :src="img.preview"
          class="max-w-[200px] rounded-xl border border-[#e8ecf2] shadow-sm"
          alt="上传的图片"
        />
      </div>

      <div
        class="rounded-bubble px-4 py-3"
        :class="[
          isUser
            ? 'bg-primary-500 text-white rounded-br-sm'
            : 'bg-white border border-[#e8ecf2] rounded-bl-sm shadow-card',
          message.isError ? 'bg-red-50 border-red-200' : '',
        ]"
      >
        <div
          v-if="!isUser && message.intent"
          class="flex items-center space-x-2 mb-2 pb-2 border-b border-[#e8ecf2]"
        >
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="message.intent === 'sql' ? 'bg-blue-50 text-blue-600' : 'bg-green-50 text-green-600'"
          >
            {{ getIntentLabel(message.intent) }}
          </span>
        </div>

        <div
          class="message-content prose prose-sm max-w-none"
          :class="[
            isUser ? 'prose-invert text-white' : 'text-text-primary',
            message.isStreaming ? 'typing-cursor' : '',
          ]"
          v-html="renderedHtml"
        ></div>
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

.message-content a {
  color: #3b82f6;
  text-decoration: underline;
  font-weight: 500;
}

.message-content a:hover {
  color: #2563eb;
}
</style>
