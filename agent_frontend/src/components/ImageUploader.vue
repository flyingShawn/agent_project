<script setup>
const emit = defineEmits(['select'])

const handleFileSelect = (event) => {
  const files = event.target.files
  if (!files || files.length === 0) return

  for (const file of files) {
    if (file.type.startsWith('image/')) {
      emit('select', file)
    }
  }

  event.target.value = ''
}

const triggerFileInput = () => {
  document.getElementById('image-input')?.click()
}
</script>

<template>
  <div class="flex-shrink-0">
    <input
      id="image-input"
      type="file"
      accept="image/*"
      multiple
      class="hidden"
      @change="handleFileSelect"
    />

    <button
      @click="triggerFileInput"
      class="w-8 h-8 text-text-tertiary hover:text-primary-500 rounded-full transition-colors flex items-center justify-center cursor-pointer"
      title="上传图片"
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    </button>
  </div>
</template>
