<script setup>
const props = defineProps({
  mode: {
    type: String,
    default: 'chat',
  },
})

const emit = defineEmits(['update:mode'])
</script>

<template>
  <div class="mode-toggle flex items-center gap-1 px-1 py-0.5 bg-surface-muted rounded-lg">
    <button
      @click="emit('update:mode', 'chat')"
      class="mode-tab flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 cursor-pointer"
      :class="mode === 'chat'
        ? 'bg-white text-primary-600 shadow-sm'
        : 'text-text-tertiary hover:text-text-secondary'"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
      <span>聊天</span>
    </button>
    <button
      @click="emit('update:mode', 'task')"
      class="mode-tab flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 cursor-pointer"
      :class="mode === 'task'
        ? 'bg-white text-primary-600 shadow-sm'
        : 'text-text-tertiary hover:text-text-secondary'"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
      <span>任务</span>
    </button>
  </div>
</template>
