<script setup>
const props = defineProps({
  task: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['select'])

const iconMap = {
  upload: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>`,
  image: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>`,
  leaf: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>`,
  monitor: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>`,
  task: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>`,
}
</script>

<template>
  <button
    @click="emit('select', task)"
    class="task-card group bg-white border border-[#e8ecf2] rounded-2xl p-5 text-left transition-all duration-200 hover:shadow-lg hover:border-primary-200 hover:-translate-y-0.5 cursor-pointer"
  >
    <div class="flex items-start gap-3.5">
      <div
        class="flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center transition-colors duration-200"
        :class="{
          'bg-blue-50 text-blue-500 group-hover:bg-blue-100': task.icon === 'upload',
          'bg-purple-50 text-purple-500 group-hover:bg-purple-100': task.icon === 'image',
          'bg-green-50 text-green-500 group-hover:bg-green-100': task.icon === 'leaf',
          'bg-orange-50 text-orange-500 group-hover:bg-orange-100': task.icon === 'monitor',
          'bg-gray-50 text-gray-500 group-hover:bg-gray-100': !['upload', 'image', 'leaf', 'monitor'].includes(task.icon),
        }"
        v-html="iconMap[task.icon] || iconMap.task"
      />
      <div class="flex-1 min-w-0">
        <h3 class="text-sm font-semibold text-text-primary mb-1">{{ task.name }}</h3>
        <p class="text-xs text-text-tertiary line-clamp-2 leading-relaxed">{{ task.description }}</p>
      </div>
    </div>
  </button>
</template>
