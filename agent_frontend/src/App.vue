<script setup>
import { onMounted, ref } from 'vue'
import ChatBox from './components/ChatBox.vue'
import OpsReportInbox from './components/OpsReportInbox.vue'
import Sidebar from './components/Sidebar.vue'
import config from './config'
import { useConversations } from './composables/useConversations'

const userName = ref('admin')
const showSidebar = ref(false)
const showOpsInbox = ref(false)
const unreadOpsCount = ref(0)
const chatBoxRef = ref(null)

const {
  currentTitle,
  currentConversationId,
  startNewConversation,
  loadConversations,
  switchConversation,
  conversations,
} = useConversations()

function toggleSidebar() {
  showSidebar.value = !showSidebar.value
}

function toggleOpsInbox() {
  showOpsInbox.value = !showOpsInbox.value
}

async function handleNewConversation() {
  startNewConversation()
  if (chatBoxRef.value) {
    chatBoxRef.value.handleNewSession()
  }
}

async function handleSwitchConversation(id) {
  const data = await switchConversation(id)
  if (data && chatBoxRef.value) {
    chatBoxRef.value.loadConversation(data)
  }
}

function handleDeleteConversation() {
  if (!currentConversationId.value && chatBoxRef.value) {
    chatBoxRef.value.handleNewSession()
  }
}

function handleConversationCreated() {
  loadConversations(userName.value)
}

function handleConversationUpdated() {
  loadConversations(userName.value)
}

function handleOpsUnreadChange(count) {
  unreadOpsCount.value = Number(count || 0)
}

onMounted(async () => {
  const urlParams = new URLSearchParams(window.location.search)
  userName.value = urlParams.get('user') || urlParams.get('lognum') || 'admin'
  await loadConversations(userName.value)
  if (conversations.value.length > 0) {
    showSidebar.value = true
  }
})
</script>

<template>
  <div class="h-screen flex flex-row bg-surface-muted overflow-hidden">
    <div
      class="flex-shrink-0 bg-white border-r border-[#e8ecf2] flex flex-col h-full transition-all duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden"
      :class="showSidebar ? 'w-72' : 'w-0 border-r-0'"
    >
      <Sidebar
        @new-conversation="handleNewConversation"
        @switch-conversation="handleSwitchConversation"
        @delete-conversation="handleDeleteConversation"
      />
    </div>

    <div class="flex-1 flex flex-col min-w-0">
      <header class="bg-white border-b border-[#e8ecf2] px-5 py-2.5 flex items-center justify-between relative z-10 flex-shrink-0">
        <div class="flex items-center">
          <button
            @click="toggleSidebar"
            class="rounded-xl border transition-colors cursor-pointer"
            :class="showSidebar
              ? 'border-primary-200 bg-primary-50 px-2.5 py-2 text-primary-600'
              : 'border-transparent px-2.5 py-2 text-text-tertiary hover:text-text-primary hover:bg-surface-hover'"
            :title="showSidebar ? '收起历史侧栏' : '展开历史侧栏'"
          >
            <svg class="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="3.75" y="4.75" width="16.5" height="14.5" rx="2.5" stroke-width="1.5" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.5 5.5v13" />
              <path stroke-linecap="round" stroke-width="1.8" d="M6.5 8.5h.01M6.5 12h.01M6.5 15.5h.01" />
            </svg>
          </button>
        </div>

        <div class="absolute left-1/2 -translate-x-1/2 text-center select-none">
          <h1 class="text-[15px] font-semibold text-text-primary leading-tight">{{ currentTitle }}</h1>
          <p class="text-[11px] text-text-tertiary mt-0.5">{{ config.subtitle }}</p>
        </div>

        <div class="flex items-center gap-2">
          <button
            @click="toggleOpsInbox"
            class="relative flex items-center gap-2 px-3 py-1.5 border border-[#e8ecf2] bg-white text-text-secondary hover:text-text-primary hover:bg-surface-hover rounded-lg transition-colors cursor-pointer"
            title="运维简报"
          >
            <span v-if="unreadOpsCount > 0" class="absolute right-2 top-1.5 w-2 h-2 rounded-full bg-rose-500"></span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M9 17h6M9 13h6M9 9h6M5 5h14v14H5z" />
            </svg>
            <span class="text-[12px] font-medium">运维简报</span>
          </button>

          <div class="flex items-center space-x-1.5 text-text-secondary bg-surface-muted pl-2.5 pr-3 py-1 rounded-full">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <span class="text-[11px] font-medium">{{ userName }}</span>
          </div>
        </div>
      </header>

      <main class="flex-1 overflow-hidden flex justify-center px-4 sm:px-6">
        <div class="w-full max-w-chat h-full">
          <ChatBox
            ref="chatBoxRef"
            :user-name="userName"
            @conversation-created="handleConversationCreated"
            @conversation-updated="handleConversationUpdated"
          />
        </div>
      </main>
    </div>

    <OpsReportInbox
      :open="showOpsInbox"
      @close="showOpsInbox = false"
      @unread-change="handleOpsUnreadChange"
    />
  </div>
</template>
