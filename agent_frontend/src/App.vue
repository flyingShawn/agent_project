<script setup>
import { ref, onMounted } from 'vue'
import ChatBox from './components/ChatBox.vue'
import config from './config'

const userName = ref('admin')
const showSidebar = ref(false)

const toggleSidebar = () => {
  showSidebar.value = !showSidebar.value
}

onMounted(() => {
  const urlParams = new URLSearchParams(window.location.search)
  userName.value = urlParams.get('user') || urlParams.get('lognum') || 'admin'
})
</script>

<template>
  <div class="h-screen flex flex-col bg-surface-muted">
    <header class="bg-white border-b border-[#e8ecf2] px-5 py-2.5 flex items-center justify-between relative z-10">
      <div class="flex items-center">
        <button
          @click="toggleSidebar"
          class="p-2 -ml-1.5 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded-lg transition-colors cursor-pointer"
          title="历史会话"
        >
          <svg class="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>

      <div class="absolute left-1/2 -translate-x-1/2 text-center select-none">
        <h1 class="text-[15px] font-semibold text-text-primary leading-tight">新对话</h1>
        <p class="text-[11px] text-text-tertiary mt-0.5">{{ config.subtitle }}</p>
      </div>

      <div class="flex items-center">
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
        <ChatBox :user-name="userName" :show-sidebar="showSidebar" @close-sidebar="showSidebar = false" />
      </div>
    </main>
  </div>
</template>
