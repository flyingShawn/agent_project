<script setup>
import { ref, onMounted, nextTick } from 'vue'
import ChatBox from './components/ChatBox.vue'

const userName = ref('admin')

onMounted(() => {
  const urlParams = new URLSearchParams(window.location.search)
  userName.value = urlParams.get('user') || urlParams.get('lognum') || 'admin'
})
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50">
    <header class="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm">
      <div class="flex items-center space-x-3">
        <div class="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
          </svg>
        </div>
        <div>
          <h1 class="text-lg font-semibold text-gray-800">AI 智能助手</h1>
          <p class="text-xs text-gray-500">桌管系统智能问答</p>
        </div>
      </div>
      <div class="flex items-center space-x-2 text-sm text-gray-500">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
        </svg>
        <span>{{ userName }}</span>
      </div>
    </header>
    
    <main class="flex-1 overflow-hidden">
      <ChatBox :user-name="userName" />
    </main>
  </div>
</template>
