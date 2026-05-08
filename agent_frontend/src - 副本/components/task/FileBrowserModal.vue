<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { browseFilesystem } from '../../api/tasks'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  agentType: {
    type: String,
    default: '',
  },
  multiple: {
    type: Boolean,
    default: true,
  },
  fileType: {
    type: String,
    default: 'all',
  },
  title: {
    type: String,
    default: '选择文件',
  },
})

const emit = defineEmits(['close', 'confirm'])

const currentPath = ref('')
const parentPath = ref(null)
const items = ref([])
const loading = ref(false)
const selectedPaths = ref([])
const error = ref('')

const displayPath = computed(() => currentPath.value || '此电脑')

async function loadDirectory(path = '') {
  loading.value = true
  error.value = ''
  try {
    const data = await browseFilesystem(props.agentType, path, props.fileType)
    currentPath.value = data.path || ''
    parentPath.value = data.parent
    items.value = data.items || []
  } catch (e) {
    error.value = e.message || '加载目录失败'
    items.value = []
  } finally {
    loading.value = false
  }
}

function navigateTo(path) {
  loadDirectory(path)
}

function goUp() {
  if (parentPath.value !== null && parentPath.value !== undefined) {
    loadDirectory(parentPath.value)
  }
}

function toggleSelect(item) {
  if (item.type === 'dir') {
    loadDirectory(item.path)
    return
  }

  if (props.multiple) {
    const idx = selectedPaths.value.indexOf(item.path)
    if (idx >= 0) {
      selectedPaths.value.splice(idx, 1)
    } else {
      selectedPaths.value.push(item.path)
    }
  } else {
    selectedPaths.value = [item.path]
  }
}

function isSelected(path) {
  return selectedPaths.value.includes(path)
}

function removeSelected(path) {
  const idx = selectedPaths.value.indexOf(path)
  if (idx >= 0) {
    selectedPaths.value.splice(idx, 1)
  }
}

function handleConfirm() {
  if (props.multiple) {
    emit('confirm', selectedPaths.value)
  } else {
    emit('confirm', selectedPaths.value.length > 0 ? selectedPaths.value[0] : '')
  }
}

function handleClose() {
  emit('close')
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
}

function getFileName(path) {
  const parts = path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || path
}

onMounted(() => {
  if (props.open) {
    loadDirectory()
  }
})

watch(() => props.open, (newVal) => {
  if (newVal) {
    selectedPaths.value = []
    error.value = ''
    loadDirectory()
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/40" @click="handleClose"></div>

        <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden">
          <div class="flex items-center justify-between px-5 py-4 border-b border-[#e8ecf2]">
            <h3 class="text-base font-semibold text-text-primary">{{ title }}</h3>
            <button
              @click="handleClose"
              class="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-surface-hover transition-colors cursor-pointer"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="px-5 py-3 border-b border-[#e8ecf2] flex items-center gap-2">
            <button
              @click="loadDirectory()"
              class="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-surface-hover transition-colors cursor-pointer"
              title="根目录"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
            </button>
            <button
              v-if="parentPath !== null && parentPath !== undefined"
              @click="goUp"
              class="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-surface-hover transition-colors cursor-pointer"
              title="上级目录"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div class="flex-1 px-3 py-1.5 bg-surface-muted rounded-lg text-sm text-text-secondary truncate">
              {{ displayPath }}
            </div>
          </div>

          <div v-if="selectedPaths.length > 0" class="px-5 py-2.5 border-b border-[#e8ecf2] bg-primary-50/30">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-xs text-text-tertiary mr-1">已选:</span>
              <span
                v-for="path in selectedPaths"
                :key="path"
                class="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-100 text-primary-700 rounded-md text-xs"
              >
                <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span class="max-w-[200px] truncate">{{ getFileName(path) }}</span>
                <button
                  @click.stop="removeSelected(path)"
                  class="ml-0.5 text-primary-400 hover:text-primary-600 cursor-pointer"
                >
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            </div>
          </div>

          <div class="flex-1 overflow-y-auto min-h-[300px]">
            <div v-if="loading" class="flex items-center justify-center py-12 text-sm text-text-tertiary">
              <svg class="w-5 h-5 mr-2 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              加载中...
            </div>

            <div v-else-if="error" class="flex flex-col items-center justify-center py-12 text-sm text-red-500">
              <svg class="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              {{ error }}
            </div>

            <div v-else-if="items.length === 0" class="flex flex-col items-center justify-center py-12 text-sm text-text-tertiary">
              <svg class="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              空目录
            </div>

            <div v-else class="divide-y divide-[#e8ecf2]">
              <button
                v-for="item in items"
                :key="item.path"
                @click="toggleSelect(item)"
                class="w-full flex items-center gap-3 px-5 py-2.5 hover:bg-surface-hover transition-colors cursor-pointer text-left"
                :class="{ 'bg-primary-50/50': isSelected(item.path) }"
              >
                <div class="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
                  :class="item.type === 'dir' ? 'bg-amber-50 text-amber-500' : 'bg-blue-50 text-blue-500'"
                >
                  <svg v-if="item.type === 'dir'" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                  <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-sm text-text-primary truncate">{{ item.name }}</p>
                  <p v-if="item.type === 'file' && item.size !== null" class="text-xs text-text-tertiary">{{ formatSize(item.size) }}</p>
                </div>
                <div v-if="item.type === 'file'" class="flex-shrink-0">
                  <div
                    class="w-4 h-4 rounded border-2 transition-colors"
                    :class="isSelected(item.path)
                      ? 'bg-primary-500 border-primary-500'
                      : 'border-gray-300'"
                  >
                    <svg v-if="isSelected(item.path)" class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                </div>
                <svg v-else class="w-4 h-4 text-text-tertiary flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          <div class="px-5 py-4 border-t border-[#e8ecf2] flex items-center justify-end gap-3">
            <button
              @click="handleClose"
              class="px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-hover rounded-xl transition-colors cursor-pointer"
            >
              取消
            </button>
            <button
              @click="handleConfirm"
              :disabled="selectedPaths.length === 0"
              class="px-5 py-2 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              确认选择{{ selectedPaths.length > 0 ? ` (${selectedPaths.length})` : '' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
