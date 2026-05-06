<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  addKnowledgeEntry,
  createKnowledgeFile,
  deleteKnowledgeEntry,
  fetchKnowledgeEntries,
  fetchKnowledgeFiles,
  renameKnowledgeFile,
  updateKnowledgeEntry,
} from '../api/knowledge'

const props = defineProps({
  agentType: {
    type: String,
    default: '',
  },
  editorName: {
    type: String,
    default: '',
  },
})

const kbTypes = [
  { value: 'solution', label: '问题解答' },
  { value: 'sql', label: '数据查询' },
]

const activeType = ref('solution')
const files = ref([])
const entries = ref([])
const selectedFile = ref('')
const baseDir = ref('')
const newFileName = ref('')
const renameName = ref('')
const form = ref(createEmptyForm())
const editingEntryId = ref(null)
const isLoadingFiles = ref(false)
const isLoadingEntries = ref(false)
const isSavingFile = ref(false)
const isRenamingFile = ref(false)
const isSavingEntry = ref(false)
const isDeletingEntry = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const activeTypeLabel = computed(() => {
  return kbTypes.find(item => item.value === activeType.value)?.label || ''
})

const normalizedEditorName = computed(() => props.editorName.trim())
const hasEditor = computed(() => Boolean(normalizedEditorName.value))
const canWriteCurrentType = computed(() => {
  if (!hasEditor.value) return false
  return activeType.value !== 'sql' || normalizedEditorName.value === 'admin'
})
const canDeleteEntry = computed(() => normalizedEditorName.value === 'admin')
const writeDisabledReason = computed(() => {
  if (!hasEditor.value) return '请先在右上角输入用户名'
  if (activeType.value === 'sql' && normalizedEditorName.value !== 'admin') return '该账号无权限'
  return ''
})
const isEditingEntry = computed(() => editingEntryId.value !== null)

function createEmptyForm() {
  return {
    title: '',
    scenario: '',
    keyTables: '',
    sqlCode: '',
    answer: '',
  }
}

function clearMessages() {
  errorMessage.value = ''
  successMessage.value = ''
}

function setError(error) {
  errorMessage.value = error?.message || String(error || '操作失败')
  successMessage.value = ''
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function resetEntryForm() {
  form.value = createEmptyForm()
  editingEntryId.value = null
}

function ensureWritable() {
  if (!canWriteCurrentType.value) {
    errorMessage.value = writeDisabledReason.value
    successMessage.value = ''
    return false
  }
  return true
}

async function loadFiles(preferredFile = '') {
  if (!props.agentType) return
  isLoadingFiles.value = true
  clearMessages()
  try {
    const data = await fetchKnowledgeFiles(props.agentType, activeType.value)
    files.value = data.files || []
    baseDir.value = data.base_dir || ''
    if (preferredFile && files.value.some(file => file.name === preferredFile)) {
      selectedFile.value = preferredFile
    } else if (!selectedFile.value || !files.value.some(file => file.name === selectedFile.value)) {
      selectedFile.value = files.value[0]?.name || ''
    }
    renameName.value = selectedFile.value
    await loadEntries()
  } catch (error) {
    files.value = []
    entries.value = []
    selectedFile.value = ''
    setError(error)
  } finally {
    isLoadingFiles.value = false
  }
}

async function loadEntries() {
  if (!props.agentType || !selectedFile.value) {
    entries.value = []
    return
  }
  isLoadingEntries.value = true
  clearMessages()
  try {
    const data = await fetchKnowledgeEntries(props.agentType, activeType.value, selectedFile.value)
    entries.value = data.entries || []
  } catch (error) {
    entries.value = []
    setError(error)
  } finally {
    isLoadingEntries.value = false
  }
}

async function handleCreateFile() {
  if (!ensureWritable()) return
  const name = newFileName.value.trim()
  if (!name) return
  isSavingFile.value = true
  clearMessages()
  try {
    const data = await createKnowledgeFile(props.agentType, activeType.value, name, normalizedEditorName.value)
    const createdName = data.file?.name || ''
    newFileName.value = ''
    await loadFiles(createdName)
    successMessage.value = '文件已创建'
  } catch (error) {
    setError(error)
  } finally {
    isSavingFile.value = false
  }
}

async function handleRenameFile() {
  if (!ensureWritable()) return
  if (!selectedFile.value) return
  const name = renameName.value.trim()
  if (!name || name === selectedFile.value) return
  isRenamingFile.value = true
  clearMessages()
  try {
    const data = await renameKnowledgeFile(
      props.agentType,
      activeType.value,
      selectedFile.value,
      name,
      normalizedEditorName.value,
    )
    const renamedName = data.file?.name || name
    await loadFiles(renamedName)
    successMessage.value = '文件已重命名'
  } catch (error) {
    setError(error)
  } finally {
    isRenamingFile.value = false
  }
}

async function handleSaveEntry() {
  if (!ensureWritable()) return
  if (!selectedFile.value) return
  isSavingEntry.value = true
  clearMessages()
  try {
    const payload = {
      filename: selectedFile.value,
      kbType: activeType.value,
      title: form.value.title,
      scenario: form.value.scenario,
      keyTables: form.value.keyTables,
      sqlCode: form.value.sqlCode,
      answer: form.value.answer,
      editorName: normalizedEditorName.value,
    }
    if (editingEntryId.value) {
      await updateKnowledgeEntry(props.agentType, {
        ...payload,
        entryId: editingEntryId.value,
      })
    } else {
      await addKnowledgeEntry(props.agentType, payload)
    }
    resetEntryForm()
    await loadFiles(selectedFile.value)
    successMessage.value = '保存成功'
  } catch (error) {
    setError(error)
  } finally {
    isSavingEntry.value = false
  }
}

function selectType(type) {
  if (activeType.value === type) return
  activeType.value = type
}

function selectFile(fileName) {
  selectedFile.value = fileName
  renameName.value = fileName
  resetEntryForm()
  loadEntries()
}

function startEditEntry(entry) {
  if (!ensureWritable()) return
  editingEntryId.value = entry.id
  form.value = {
    title: entry.title || '',
    scenario: entry.scenario || '',
    keyTables: entry.key_tables || '',
    sqlCode: entry.sql_code || '',
    answer: entry.answer || '',
  }
}

async function handleDeleteEntry(entry) {
  if (!canDeleteEntry.value) {
    errorMessage.value = hasEditor.value ? '该账号无权限' : writeDisabledReason.value
    successMessage.value = ''
    return
  }
  if (!selectedFile.value || !entry.id) return
  if (!window.confirm('确认删除这条记录？')) return
  isDeletingEntry.value = true
  clearMessages()
  try {
    await deleteKnowledgeEntry(props.agentType, {
      filename: selectedFile.value,
      entryId: entry.id,
      kbType: activeType.value,
      editorName: normalizedEditorName.value,
    })
    if (editingEntryId.value === entry.id) {
      resetEntryForm()
    }
    await loadFiles(selectedFile.value)
    successMessage.value = '删除成功'
  } catch (error) {
    setError(error)
  } finally {
    isDeletingEntry.value = false
  }
}

watch(activeType, () => {
  selectedFile.value = ''
  renameName.value = ''
  entries.value = []
  resetEntryForm()
  loadFiles()
})

watch(() => props.agentType, () => {
  selectedFile.value = ''
  renameName.value = ''
  entries.value = []
  resetEntryForm()
  loadFiles()
})

onMounted(() => loadFiles())
</script>

<template>
  <div class="h-full overflow-y-auto no-scrollbar py-5">
    <div class="mx-auto flex h-full w-full max-w-[1680px] flex-col gap-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 class="text-xl font-semibold leading-tight text-text-primary">知识库</h2>
          <p class="mt-1 text-xs text-text-tertiary">{{ baseDir || '本地 Markdown 文件' }}</p>
        </div>
        <div class="inline-flex w-fit items-center gap-1 rounded-lg bg-white p-1 border border-[#e8ecf2]">
          <button
            v-for="item in kbTypes"
            :key="item.value"
            @click="selectType(item.value)"
            class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer"
            :class="activeType === item.value
              ? 'bg-primary-50 text-primary-600'
              : 'text-text-tertiary hover:bg-surface-hover hover:text-text-secondary'"
          >
            {{ item.label }}
          </button>
        </div>
      </div>

      <div
        v-if="errorMessage || successMessage"
        class="rounded-lg border px-3 py-2 text-sm"
        :class="errorMessage ? 'border-red-200 bg-red-50 text-red-600' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
      >
        {{ errorMessage || successMessage }}
      </div>
      <div
        v-if="writeDisabledReason"
        class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700"
      >
        {{ writeDisabledReason }}
      </div>

      <div class="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside class="flex min-h-[360px] flex-col rounded-lg border border-[#e8ecf2] bg-white">
          <div class="border-b border-[#eef2f6] p-4">
            <p class="mb-2 text-xs font-medium text-text-tertiary">新建 .md 文件</p>
            <div class="flex gap-2">
              <input
                v-model="newFileName"
                @keydown.enter.prevent="handleCreateFile"
                :disabled="!canWriteCurrentType"
                class="min-w-0 flex-1 rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm focus:border-primary-400 focus:outline-none"
                placeholder="文件名"
              />
              <button
                @click="handleCreateFile"
                :disabled="isSavingFile || !newFileName.trim() || !canWriteCurrentType"
                class="rounded-lg bg-primary-500 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-600 disabled:bg-gray-300 disabled:cursor-not-allowed cursor-pointer"
              >
                新建
              </button>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto p-2">
            <div v-if="isLoadingFiles" class="py-8 text-center text-sm text-text-tertiary">加载中...</div>
            <div v-else-if="files.length === 0" class="py-8 text-center text-sm text-text-tertiary">暂无 .md 文件</div>
            <template v-else>
              <button
                v-for="file in files"
                :key="file.name"
                @click="selectFile(file.name)"
                class="mb-1 w-full rounded-lg px-3 py-2.5 text-left transition-colors cursor-pointer"
                :class="selectedFile === file.name ? 'bg-primary-50 text-primary-600' : 'text-text-secondary hover:bg-surface-hover'"
              >
                <span class="block truncate text-sm font-medium">{{ file.name }}</span>
                <span class="mt-0.5 block text-[11px] text-text-tertiary">
                  {{ file.entry_count }} 条 · {{ formatTime(file.updated_at) }}
                </span>
              </button>
            </template>
          </div>
        </aside>

        <section class="min-h-[560px] overflow-hidden rounded-lg border border-[#e8ecf2] bg-white">
          <div class="flex flex-col gap-3 border-b border-[#eef2f6] p-4 md:flex-row md:items-center md:justify-between">
            <div class="min-w-0">
              <p class="text-sm font-semibold text-text-primary">{{ selectedFile || '未选择文件' }}</p>
              <p class="mt-0.5 text-xs text-text-tertiary">{{ activeTypeLabel }} · {{ entries.length }} 条</p>
            </div>
            <div class="flex min-w-0 gap-2">
              <input
                v-model="renameName"
                :disabled="!selectedFile || !canWriteCurrentType"
                class="min-w-0 flex-1 rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm focus:border-primary-400 focus:outline-none disabled:bg-surface-muted"
                placeholder="重命名文件"
              />
              <button
                @click="handleRenameFile"
                :disabled="isRenamingFile || !selectedFile || !renameName.trim() || renameName === selectedFile || !canWriteCurrentType"
                class="rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-hover disabled:text-text-tertiary disabled:cursor-not-allowed cursor-pointer"
              >
                重命名
              </button>
            </div>
          </div>

          <div class="grid h-[calc(100%_-_73px)] grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1fr)_460px]">
            <div class="min-h-0 overflow-y-auto border-b border-[#eef2f6] p-4 xl:border-b-0 xl:border-r">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold text-text-primary">已保存内容</h3>
                <button
                  @click="loadEntries"
                  :disabled="!selectedFile || isLoadingEntries"
                  class="text-xs text-text-tertiary transition-colors hover:text-primary-500 disabled:cursor-not-allowed cursor-pointer"
                >
                  刷新
                </button>
              </div>

              <div v-if="!selectedFile" class="py-16 text-center text-sm text-text-tertiary">先选择或新建一个文件</div>
              <div v-else-if="isLoadingEntries" class="py-16 text-center text-sm text-text-tertiary">加载中...</div>
              <div v-else-if="entries.length === 0" class="py-16 text-center text-sm text-text-tertiary">暂无已保存内容</div>
              <div v-else class="space-y-2">
                <details
                  v-for="(entry, index) in entries"
                  :key="entry.id || entry.title + index"
                  class="rounded-lg border border-[#e8ecf2] bg-white p-3 open:bg-surface-muted/50"
                >
                  <summary class="cursor-pointer list-none">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0">
                        <p class="truncate text-sm font-medium text-text-primary">{{ entry.title }}</p>
                        <p class="mt-1 line-clamp-2 text-xs leading-5 text-text-tertiary">{{ entry.scenario }}</p>
                      </div>
                      <span class="shrink-0 rounded-md bg-surface-muted px-2 py-0.5 text-[11px] text-text-tertiary">展开</span>
                    </div>
                  </summary>
                  <div class="mt-3 border-t border-[#eef2f6] pt-3">
                    <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div class="text-[11px] leading-5 text-text-tertiary">
                        创建：{{ entry.created_by || '-' }} · {{ formatTime(entry.created_at) || '-' }}
                        <span class="mx-1">/</span>
                        编辑：{{ entry.updated_by || '-' }} · {{ formatTime(entry.updated_at) || '-' }}
                      </div>
                      <div class="flex items-center gap-2">
                        <button
                          @click="startEditEntry(entry)"
                          :disabled="!canWriteCurrentType"
                          class="w-fit rounded-md border border-[#d9d9e3] px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-white hover:text-primary-500 disabled:text-text-tertiary disabled:cursor-not-allowed cursor-pointer"
                        >
                          编辑
                        </button>
                        <button
                          v-if="canDeleteEntry"
                          @click="handleDeleteEntry(entry)"
                          :disabled="isDeletingEntry"
                          class="w-fit rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:text-text-tertiary disabled:cursor-not-allowed cursor-pointer"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                    <p v-if="activeType === 'sql'" class="mb-2 text-xs text-text-tertiary">关键表：{{ entry.key_tables }}</p>
                    <pre
                      v-if="activeType === 'sql'"
                      class="max-h-[360px] overflow-auto rounded-lg bg-gray-900 p-3 text-xs leading-5 text-gray-100"
                    >{{ entry.sql_code }}</pre>
                    <p v-else class="whitespace-pre-wrap text-sm leading-6 text-text-secondary">{{ entry.answer }}</p>
                  </div>
                </details>
              </div>
            </div>

            <form class="min-h-0 overflow-y-auto p-4" @submit.prevent="handleSaveEntry">
              <div class="mb-3 flex items-center justify-between gap-2">
                <h3 class="text-sm font-semibold text-text-primary">
                  {{ isEditingEntry ? '编辑' : '录入' }}{{ activeTypeLabel }}
                </h3>
                <button
                  v-if="isEditingEntry"
                  type="button"
                  @click="resetEntryForm"
                  class="text-xs text-text-tertiary transition-colors hover:text-text-secondary cursor-pointer"
                >
                  取消编辑
                </button>
              </div>
              <fieldset :disabled="!selectedFile || isSavingEntry || !canWriteCurrentType" class="space-y-3 disabled:opacity-60">
                <label class="block">
                  <span class="mb-1 block text-xs font-medium text-text-secondary">标题</span>
                  <input
                    v-model="form.title"
                    class="w-full rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm focus:border-primary-400 focus:outline-none"
                    required
                  />
                </label>

                <label class="block">
                  <span class="mb-1 block text-xs font-medium text-text-secondary">适用场景</span>
                  <textarea
                    v-model="form.scenario"
                    class="min-h-[96px] w-full resize-y rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm leading-6 focus:border-primary-400 focus:outline-none"
                    required
                  ></textarea>
                </label>

                <template v-if="activeType === 'sql'">
                  <label class="block">
                    <span class="mb-1 block text-xs font-medium text-text-secondary">关键表</span>
                    <input
                      v-model="form.keyTables"
                      class="w-full rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm focus:border-primary-400 focus:outline-none"
                      placeholder="s_Machine, s_Group"
                      required
                    />
                  </label>

                  <label class="block">
                    <span class="mb-1 block text-xs font-medium text-text-secondary">SQL代码</span>
                    <textarea
                      v-model="form.sqlCode"
                      class="min-h-[220px] w-full resize-y rounded-lg border border-[#d9d9e3] px-3 py-2 font-mono text-sm leading-6 focus:border-primary-400 focus:outline-none"
                      spellcheck="false"
                      required
                    ></textarea>
                  </label>
                </template>

                <label v-else class="block">
                  <span class="mb-1 block text-xs font-medium text-text-secondary">解答内容</span>
                  <textarea
                    v-model="form.answer"
                    class="min-h-[300px] w-full resize-y rounded-lg border border-[#d9d9e3] px-3 py-2 text-sm leading-6 focus:border-primary-400 focus:outline-none"
                    required
                  ></textarea>
                </label>

                <button
                  type="submit"
                  :disabled="!selectedFile || isSavingEntry || !canWriteCurrentType"
                  class="w-full rounded-lg bg-primary-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-600 disabled:bg-gray-300 disabled:cursor-not-allowed cursor-pointer"
                >
                  {{ isSavingEntry ? '保存中...' : '保存' }}
                </button>
              </fieldset>
            </form>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
