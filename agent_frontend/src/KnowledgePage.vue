<script setup>
import { computed, onMounted, ref } from 'vue'
import KnowledgeBasePanel from './components/KnowledgeBasePanel.vue'
import config from './config'
import {
  readExternalIdentityFromLocation,
  setExternalIdentity,
} from './utils/externalIdentity'

defineProps({
  agentType: { type: String, default: '' },
})

const STORAGE_KEY = 'knowledge_editor_name'
const editorName = ref('')
const draftName = ref('')
const editingUser = ref(false)
const loginError = ref('')

const DISPLAY_NAME_MAP = { su: 'super' }
const DISABLED_USERNAMES = ['super']

const displayName = computed(() => {
  if (!editorName.value) return '未登录'
  return DISPLAY_NAME_MAP[editorName.value.trim()] || editorName.value.trim()
})

onMounted(() => {
  setExternalIdentity(readExternalIdentityFromLocation())
  editorName.value = localStorage.getItem(STORAGE_KEY) || ''
  draftName.value = editorName.value
})

function startEditUser() {
  draftName.value = editorName.value
  editingUser.value = true
}

function saveUser() {
  const name = draftName.value.trim()
  loginError.value = ''
  if (DISABLED_USERNAMES.includes(name)) {
    loginError.value = '该账号已禁用'
    return
  }
  editorName.value = name
  if (name) {
    localStorage.setItem(STORAGE_KEY, name)
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
  editingUser.value = false
}
</script>

<template>
  <div class="h-screen overflow-hidden bg-surface-muted">
    <header class="border-b border-[#e8ecf2] bg-white px-5 py-3">
      <div class="mx-auto flex w-full max-w-[1680px] items-center justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <img
            src="/logo.png"
            alt="logo"
            class="h-8 w-8 shrink-0 rounded-lg object-contain"
          />
          <div class="min-w-0">
            <h1 class="truncate text-base font-semibold text-text-primary">知识库录入</h1>
            <p class="text-xs text-text-tertiary">{{ config.appName }}</p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <template v-if="editingUser">
            <div class="flex flex-col items-end gap-1">
              <div class="flex items-center gap-2">
                <input
                  v-model="draftName"
                  @keydown.enter.prevent="saveUser"
                  class="w-40 rounded-lg border border-[#d9d9e3] px-3 py-1.5 text-sm focus:border-primary-400 focus:outline-none"
                  placeholder="输入用户名"
                />
                <button
                  @click="saveUser"
                  class="rounded-lg bg-primary-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-600 cursor-pointer"
                >
                  保存
                </button>
                <button
                  @click="loginError = ''; editingUser = false; draftName = editorName"
                  class="rounded-lg border border-[#d9d9e3] px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-hover cursor-pointer"
                >
                  取消
                </button>
              </div>
              <p v-if="loginError" class="text-xs text-red-500">{{ loginError }}</p>
            </div>
          </template>
          <button
            v-else
            @click="startEditUser"
            class="rounded-lg border border-[#e8ecf2] bg-white px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary cursor-pointer"
          >
            {{ displayName }}
          </button>
        </div>
      </div>
    </header>

    <main class="h-[calc(100vh_-_57px)] px-4 sm:px-6">
      <KnowledgeBasePanel
        :agent-type="agentType"
        :editor-name="editorName"
      />
    </main>
  </div>
</template>
