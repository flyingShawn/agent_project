<script setup>
import { ref, nextTick } from 'vue'
import { useConversations } from '../composables/useConversations'
import config from '../config'

const emit = defineEmits(['new-conversation', 'switch-conversation', 'delete-conversation'])

const {
  conversations,
  currentConversationId,
  loadConversations,
  renameConversation,
  removeConversation,
} = useConversations()

const editingId = ref(null)
const editingTitle = ref('')
const editInputRef = ref(null)
const deletingId = ref(null)

async function handleNewConversation() {
  emit('new-conversation')
}

async function handleSwitchConversation(id) {
  if (editingId.value || deletingId.value) return
  emit('switch-conversation', id)
}

function requestDelete(id, event) {
  event.stopPropagation()
  deletingId.value = id
}

function cancelDelete() {
  deletingId.value = null
}

async function confirmDelete(id) {
  const result = await removeConversation(id)
  if (result.success) {
    emit('delete-conversation', id)
  }
  deletingId.value = null
}

function startEditing(conv, event) {
  event.stopPropagation()
  editingId.value = conv.id
  editingTitle.value = conv.title
  nextTick(() => {
    const inputs = document.querySelectorAll('.edit-input-' + conv.id)
    const input = inputs.length > 0 ? inputs[0] : null
    if (input) {
      input.focus()
      input.select()
    }
  })
}

async function finishEditing(conv) {
  const newTitle = editingTitle.value.trim()
  if (newTitle && newTitle !== conv.title) {
    await renameConversation(conv.id, newTitle)
  }
  editingId.value = null
  editingTitle.value = ''
}

function cancelEditing() {
  editingId.value = null
  editingTitle.value = ''
}

function handleEditKeydown(event, conv) {
  if (event.key === 'Enter') {
    event.preventDefault()
    finishEditing(conv)
  } else if (event.key === 'Escape') {
    cancelEditing()
  }
}

defineExpose({ loadConversations })
</script>

<template>
  <div class="min-w-[288px] flex flex-col h-full">
    <div class="px-4 pt-4 pb-4">
      <div class="flex min-w-0 items-center gap-3">
        <img
          src="/logo.png"
          alt="logo"
          class="h-9 w-9 shrink-0 rounded-lg object-contain"
        />
        <h2 class="truncate text-lg font-semibold tracking-[0.01em] text-text-primary">{{ config.appName }}</h2>
      </div>
    </div>
    <div class="px-3 pb-6">
      <button
        @click="handleNewConversation"
        class="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-primary-500 hover:bg-primary-50 rounded-lg transition-colors cursor-pointer border border-primary-200 bg-primary-50/50"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v16m8-8H4" />
        </svg>
        开启新会话
      </button>
    </div>
    <div class="px-4 pb-4">
      <div class="h-px bg-[#eef2f6]"></div>
      <p class="pt-4 text-[11px] font-medium tracking-[0.08em] text-text-tertiary">历史会话</p>
    </div>
    <div class="flex-1 overflow-y-auto px-3 pb-4 no-scrollbar">
      <div v-if="conversations.length === 0" class="text-center py-8 text-text-tertiary text-sm">
        <svg class="w-10 h-10 mx-auto mb-2 text-text-tertiary/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        暂无历史会话
      </div>
      <div v-else class="space-y-0.5">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          @click="handleSwitchConversation(conv.id)"
          class="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors"
          :class="conv.id === currentConversationId ? 'bg-primary-50 text-primary-600' : 'text-text-secondary hover:bg-surface-hover'"
          @dblclick="startEditing(conv, $event)"
        >
          <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <div v-if="editingId === conv.id" class="flex-1 min-w-0" @click.stop>
            <input
              :class="'edit-input-' + conv.id"
              v-model="editingTitle"
              @keydown="handleEditKeydown($event, conv)"
              @blur="finishEditing(conv)"
              class="w-full text-sm bg-white border border-primary-300 rounded px-1.5 py-0.5 focus:outline-none focus:border-primary-500"
              maxlength="50"
            />
          </div>
          <span v-else-if="deletingId === conv.id" class="flex-1 text-sm text-red-500 truncate">确认删除？</span>
          <span v-else class="flex-1 text-sm truncate">{{ conv.title }}</span>
          <div v-if="deletingId === conv.id" class="flex-shrink-0 flex items-center gap-0.5" @click.stop>
            <button
              @click="confirmDelete(conv.id)"
              class="px-1.5 py-0.5 text-xs text-white bg-red-500 hover:bg-red-600 rounded transition-colors cursor-pointer"
            >
              删除
            </button>
            <button
              @click="cancelDelete"
              class="px-1.5 py-0.5 text-xs text-text-tertiary hover:text-text-primary bg-gray-100 hover:bg-gray-200 rounded transition-colors cursor-pointer"
            >
              取消
            </button>
          </div>
          <div v-else class="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
            <button
              @click="startEditing(conv, $event)"
              class="p-1 text-text-tertiary hover:text-text-primary rounded transition-colors cursor-pointer"
              title="重命名"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
            </button>
            <button
              @click="requestDelete(conv.id, $event)"
              class="p-1 text-text-tertiary hover:text-red-500 rounded transition-colors cursor-pointer"
              title="删除"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
