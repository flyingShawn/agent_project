<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { fetchTaskOptions } from '../../api/tasks'
import FileBrowserModal from './FileBrowserModal.vue'

const props = defineProps({
  param: {
    type: Object,
    required: true,
  },
  modelValue: {
    default: undefined,
  },
  error: {
    type: String,
    default: '',
  },
  agentType: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue'])

const localValue = ref(props.modelValue ?? props.param.default ?? '')
const dynamicOptions = ref([])
const optionsLoading = ref(false)
const searchKeyword = ref('')
const showFileBrowser = ref(false)

const filePaths = computed(() => {
  if (Array.isArray(localValue.value)) return localValue.value
  if (typeof localValue.value === 'string' && localValue.value) return [localValue.value]
  return []
})

const isMultipleFiles = computed(() => {
  return props.param.validation?.multiple !== false
})

watch(() => props.modelValue, (val) => {
  if (val !== localValue.value) {
    localValue.value = val
  }
})

watch(localValue, (val) => {
  emit('update:modelValue', val)
})

onMounted(async () => {
  if (props.param.options_api) {
    await loadDynamicOptions()
  }
})

async function loadDynamicOptions(keyword = '') {
  if (!props.param.options_api || !props.agentType) return
  optionsLoading.value = true
  try {
    const data = await fetchTaskOptions(props.agentType, props.param.options_api, keyword)
    dynamicOptions.value = data.options || []
  } catch (e) {
    dynamicOptions.value = []
  } finally {
    optionsLoading.value = false
  }
}

function handleSelectorSearch(keyword) {
  searchKeyword.value = keyword
  loadDynamicOptions(keyword)
}

function openFileBrowser() {
  showFileBrowser.value = true
}

function handleFileSelect(paths) {
  if (isMultipleFiles.value) {
    localValue.value = Array.isArray(paths) ? paths : [paths]
  } else {
    localValue.value = Array.isArray(paths) ? (paths[0] || '') : paths
  }
  showFileBrowser.value = false
}

function removeFilePath(index) {
  if (Array.isArray(localValue.value)) {
    const newVal = [...localValue.value]
    newVal.splice(index, 1)
    localValue.value = newVal
  } else {
    localValue.value = ''
  }
}

const options = () => props.param.options || dynamicOptions.value
</script>

<template>
  <div class="task-field">
    <label class="block text-sm font-medium text-text-primary mb-1.5">
      {{ param.label }}
      <span v-if="param.required" class="text-red-400 ml-0.5">*</span>
    </label>

    <!-- TEXT -->
    <input
      v-if="param.type === 'text'"
      v-model="localValue"
      type="text"
      :placeholder="param.placeholder || ''"
      class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all"
      :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
    />

    <!-- FILE_PATH -->
    <div v-else-if="param.type === 'file_path'" class="file-path-field">
      <button
        @click="showFileBrowser = true"
        class="w-full flex items-center gap-3 px-4 py-3 bg-white border-2 border-dashed rounded-xl text-sm transition-all cursor-pointer hover:border-primary-300 hover:bg-primary-50/30"
        :class="error ? 'border-red-300' : 'border-[#d4d9e3]'"
      >
        <div class="flex-shrink-0 w-9 h-9 rounded-lg bg-primary-50 text-primary-500 flex items-center justify-center">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
        </div>
        <div class="flex-1 text-left">
          <p class="text-sm font-medium text-text-primary">点击选择文件</p>
          <p class="text-xs text-text-tertiary mt-0.5">{{ isMultipleFiles ? '从管理机选择文件，支持多选' : '从管理机选择一个文件' }}</p>
        </div>
        <svg class="w-4 h-4 text-text-tertiary flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <div v-if="filePaths.length > 0" class="mt-2.5 space-y-1.5">
        <div
          v-for="(path, index) in filePaths"
          :key="index"
          class="flex items-center gap-2 px-3 py-2 bg-primary-50/40 border border-primary-100 rounded-lg group"
        >
          <svg class="w-4 h-4 text-primary-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span class="flex-1 text-xs text-text-primary font-mono truncate">{{ path }}</span>
          <button
            @click="removeFilePath(index)"
            class="opacity-0 group-hover:opacity-100 p-0.5 rounded text-text-tertiary hover:text-red-500 transition-all cursor-pointer"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="filePaths.length > 0" class="mt-1.5 flex items-center gap-2">
        <button
          @click="showFileBrowser = true"
          class="text-xs text-primary-500 hover:text-primary-600 transition-colors cursor-pointer"
        >
          + 继续添加
        </button>
        <span class="text-xs text-text-tertiary">已选 {{ filePaths.length }} 个文件</span>
      </div>

      <p v-if="param.description" class="mt-1.5 text-xs text-text-tertiary flex items-start gap-1">
        <svg class="w-3.5 h-3.5 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {{ param.description }}
      </p>

      <FileBrowserModal
        :open="showFileBrowser"
        :agent-type="agentType"
        :multiple="isMultipleFiles"
        :title="param.label || '选择文件'"
        @close="showFileBrowser = false"
        @confirm="handleFileSelect"
      />
    </div>

    <!-- TEXTAREA -->
    <textarea
      v-else-if="param.type === 'textarea'"
      v-model="localValue"
      :placeholder="param.placeholder || ''"
      rows="3"
      class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all resize-none"
      :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
    />

    <!-- NUMBER -->
    <input
      v-else-if="param.type === 'number'"
      v-model.number="localValue"
      type="number"
      :placeholder="param.placeholder || ''"
      :min="param.validation?.min"
      :max="param.validation?.max"
      class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all"
      :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
    />

    <!-- SELECT -->
    <select
      v-else-if="param.type === 'select'"
      v-model="localValue"
      class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all appearance-none cursor-pointer"
      :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
    >
      <option value="" disabled>请选择</option>
      <option v-for="opt in options()" :key="opt.value" :value="opt.value">
        {{ opt.label }}
      </option>
    </select>

    <!-- MULTI_SELECT -->
    <div v-else-if="param.type === 'multi_select'" class="space-y-2">
      <label
        v-for="opt in options()"
        :key="opt.value"
        class="flex items-center gap-2.5 px-3 py-2 bg-white border rounded-xl cursor-pointer hover:border-primary-300 transition-all"
        :class="{
          'border-primary-400 bg-primary-50/50': Array.isArray(localValue) && localValue.includes(opt.value),
          'border-[#e8ecf2]': !Array.isArray(localValue) || !localValue.includes(opt.value),
        }"
      >
        <input
          type="checkbox"
          :checked="Array.isArray(localValue) && localValue.includes(opt.value)"
          @change="(e) => {
            const checked = e.target.checked
            const val = Array.isArray(localValue) ? [...localValue] : []
            if (checked) val.push(opt.value)
            else val.splice(val.indexOf(opt.value), 1)
            localValue = val
          }"
          class="w-4 h-4 rounded border-gray-300 text-primary-500 focus:ring-primary-400"
        />
        <span class="text-sm text-text-primary">{{ opt.label }}</span>
      </label>
    </div>

    <!-- BOOLEAN -->
    <div v-else-if="param.type === 'boolean'" class="flex items-center gap-3">
      <button
        @click="localValue = true"
        class="flex items-center gap-2 px-4 py-2 rounded-xl border text-sm font-medium transition-all cursor-pointer"
        :class="localValue === true
          ? 'border-primary-400 bg-primary-50 text-primary-600'
          : 'border-[#e8ecf2] text-text-secondary hover:border-primary-200'"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        启用
      </button>
      <button
        @click="localValue = false"
        class="flex items-center gap-2 px-4 py-2 rounded-xl border text-sm font-medium transition-all cursor-pointer"
        :class="localValue === false
          ? 'border-gray-400 bg-gray-50 text-text-primary'
          : 'border-[#e8ecf2] text-text-secondary hover:border-gray-300'"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        停用
      </button>
    </div>

    <!-- TIME -->
    <input
      v-else-if="param.type === 'time'"
      v-model="localValue"
      type="time"
      class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all"
      :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
    />

    <!-- CLIENT_SELECTOR -->
    <div v-else-if="param.type === 'client_selector'" class="client-selector">
      <div class="relative">
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索客户端名称或IP..."
          class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all pr-8"
          :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
          @input="handleSelectorSearch($event.target.value)"
        />
        <svg class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
      <div v-if="optionsLoading" class="mt-2 text-xs text-text-tertiary text-center py-2">加载中...</div>
      <div v-else-if="dynamicOptions.length > 0" class="mt-2 max-h-40 overflow-y-auto border border-[#e8ecf2] rounded-xl">
        <label
          v-for="opt in dynamicOptions"
          :key="opt.value"
          class="flex items-center gap-2.5 px-3 py-2 hover:bg-surface-hover cursor-pointer border-b border-[#e8ecf2] last:border-b-0"
        >
          <input
            type="checkbox"
            :checked="Array.isArray(localValue) && localValue.includes(opt.value)"
            @change="(e) => {
              const checked = e.target.checked
              const val = Array.isArray(localValue) ? [...localValue] : []
              if (checked) val.push(opt.value)
              else val.splice(val.indexOf(opt.value), 1)
              localValue = val
            }"
            class="w-3.5 h-3.5 rounded border-gray-300 text-primary-500 focus:ring-primary-400"
          />
          <div class="flex-1 min-w-0">
            <span class="text-sm text-text-primary">{{ opt.label }}</span>
            <span v-if="opt.detail" class="text-xs text-text-tertiary ml-2">{{ opt.detail }}</span>
          </div>
          <span
            v-if="opt.status"
            class="text-xs px-1.5 py-0.5 rounded-full"
            :class="opt.status === 'online' ? 'bg-green-50 text-green-600' : 'bg-gray-50 text-text-tertiary'"
          >
            {{ opt.status === 'online' ? '在线' : '离线' }}
          </span>
        </label>
      </div>
      <div v-if="Array.isArray(localValue) && localValue.length > 0" class="mt-2 text-xs text-text-tertiary">
        已选择 {{ localValue.length }} 个客户端
      </div>
    </div>

    <!-- DEPARTMENT_SELECTOR -->
    <div v-else-if="param.type === 'department_selector'" class="department-selector">
      <div class="relative">
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索部门名称..."
          class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all pr-8"
          :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
          @input="handleSelectorSearch($event.target.value)"
        />
        <svg class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
      <div v-if="optionsLoading" class="mt-2 text-xs text-text-tertiary text-center py-2">加载中...</div>
      <div v-else-if="dynamicOptions.length > 0" class="mt-2 max-h-40 overflow-y-auto border border-[#e8ecf2] rounded-xl">
        <label
          v-for="opt in dynamicOptions"
          :key="opt.value"
          class="flex items-center gap-2.5 px-3 py-2 hover:bg-surface-hover cursor-pointer border-b border-[#e8ecf2] last:border-b-0"
        >
          <input
            type="checkbox"
            :checked="Array.isArray(localValue) && localValue.includes(opt.value)"
            @change="(e) => {
              const checked = e.target.checked
              const val = Array.isArray(localValue) ? [...localValue] : []
              if (checked) val.push(opt.value)
              else val.splice(val.indexOf(opt.value), 1)
              localValue = val
            }"
            class="w-3.5 h-3.5 rounded border-gray-300 text-primary-500 focus:ring-primary-400"
          />
          <span class="text-sm text-text-primary">{{ opt.label }}</span>
          <span v-if="opt.count !== undefined" class="text-xs text-text-tertiary">({{ opt.count }}台设备)</span>
        </label>
      </div>
      <div v-if="Array.isArray(localValue) && localValue.length > 0" class="mt-2 text-xs text-text-tertiary">
        已选择 {{ localValue.length }} 个部门
      </div>
    </div>

    <!-- DATE -->
    <input
      v-else-if="param.type === 'date'"
      v-model="localValue"
      type="date"
      class="w-full px-3 py-2.5 bg-white border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all"
      :class="error ? 'border-red-300' : 'border-[#e8ecf2]'"
    />

    <!-- 通用描述 -->
    <p v-if="param.description && param.type !== 'file_path'" class="mt-1.5 text-xs text-text-tertiary">
      {{ param.description }}
    </p>

    <!-- 错误信息 -->
    <p v-if="error" class="mt-1.5 text-xs text-red-500">{{ error }}</p>
  </div>
</template>
