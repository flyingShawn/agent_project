<script setup>
import { onMounted, ref, computed, watch } from 'vue'
import ChatBox from './components/ChatBox.vue'
import OpsReportInbox from './components/OpsReportInbox.vue'
import Sidebar from './components/Sidebar.vue'
import TaskModePanel from './components/task/TaskModePanel.vue'
import TaskWizard from './components/task/TaskWizard.vue'
import config from './config'
import { useConversations } from './composables/useConversations'
import { useTaskMode } from './composables/useTaskMode'
import { fetchAgents } from './api/agents'
import {
  getExternalDisplayName,
  getExternalUserId,
  readExternalIdentityFromLocation,
  setExternalIdentity,
} from './utils/externalIdentity'

const props = defineProps({
  agentType: { type: String, default: '' },
})

const currentAgentType = computed(() => props.agentType)

const currentUserId = ref('admin')
const currentUserLabel = ref('admin')
const showSidebar = ref(false)
const showOpsInbox = ref(false)
const unreadOpsCount = ref(0)
const chatBoxRef = ref(null)
const reportsEnabled = ref(false)
const tasksEnabled = ref(false)
const AUTO_OPEN_SIDEBAR_MIN_WIDTH = 1280

const {
  currentTitle,
  currentConversationId,
  startNewConversation,
  loadConversations,
  switchConversation,
  conversations,
} = useConversations()

const {
  mode,
  tasks,
  selectedTask,
  taskSchema,
  currentStepIndex,
  currentStep,
  collectedParams,
  stepErrors,
  taskResult,
  isExecuting,
  isLoadingSchema,
  isLastStep,
  isFirstStep,
  progressPercent,
  loadTasks,
  selectTask,
  updateParam,
  nextStep,
  prevStep,
  submitTask,
  resetTask,
  switchMode,
  resetForAgentChange,
} = useTaskMode()

const headerTitle = computed(() => {
  return mode.value === 'task' && selectedTask.value ? selectedTask.value.name : currentTitle.value
})

const headerSubtitle = computed(() => {
  return mode.value === 'task' ? '任务模式' : config.subtitle
})

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
  const data = await switchConversation(currentAgentType.value, id)
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
  loadConversations(currentUserId.value, currentAgentType.value)
}

function handleConversationUpdated() {
  loadConversations(currentUserId.value, currentAgentType.value)
}

function handleOpsUnreadChange(count) {
  unreadOpsCount.value = Number(count || 0)
}

async function handleSelectTask(task) {
  await selectTask(currentAgentType.value, task)
}

async function handleNextStep() {
  await nextStep(currentAgentType.value)
}

async function handleSubmitTask() {
  await submitTask(currentAgentType.value)
}

function handleBackToList() {
  resetTask()
}

function handleModeChange(newMode) {
  switchMode(newMode)
}

watch(currentAgentType, (newType, oldType) => {
  if (newType !== oldType) {
    startNewConversation()
    if (chatBoxRef.value) {
      chatBoxRef.value.handleNewSession()
    }
    loadConversations(currentUserId.value, newType)
    updateReportsEnabled(newType)
    updateTasksEnabled(newType)
    resetForAgentChange()
  }
})

async function updateReportsEnabled(agentType) {
  try {
    const data = await fetchAgents()
    const agent = data.agents?.find(a => a.agent_type === agentType)
    reportsEnabled.value = agent?.reports_enabled ?? false
  } catch (e) {
    reportsEnabled.value = false
  }
}

async function updateTasksEnabled(agentType) {
  try {
    const data = await fetchAgents()
    const agent = data.agents?.find(a => a.agent_type === agentType)
    tasksEnabled.value = agent?.tasks_enabled ?? false
    if (tasksEnabled.value) {
      await loadTasks(agentType)
    }
  } catch (e) {
    tasksEnabled.value = false
  }
}

onMounted(async () => {
  const externalIdentity = setExternalIdentity(readExternalIdentityFromLocation())
  currentUserId.value = externalIdentity?.userId || getExternalUserId()
  currentUserLabel.value = externalIdentity?.displayName || getExternalDisplayName()
  await loadConversations(currentUserId.value, currentAgentType.value)
  await updateReportsEnabled(currentAgentType.value)
  await updateTasksEnabled(currentAgentType.value)
  if (window.innerWidth >= AUTO_OPEN_SIDEBAR_MIN_WIDTH && conversations.value.length > 0) {
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
        :agent-type="currentAgentType"
        :current-user-label="currentUserLabel"
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
            class="rounded-xl p-2 transition-colors cursor-pointer"
            :class="showSidebar
              ? 'bg-surface-muted text-text-primary'
              : 'text-text-tertiary hover:text-text-primary hover:bg-surface-hover'"
            :title="showSidebar ? '收起历史侧栏' : '展开历史侧栏'"
          >
            <svg class="h-[24px] w-[24px]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="4.25" y="5" width="15.5" height="14" rx="2.75" stroke-width="1.5" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10 5.75v12.5" />
            </svg>
          </button>
        </div>

        <div class="absolute left-1/2 -translate-x-1/2 text-center select-none">
          <h1 class="text-[15px] font-semibold text-text-primary leading-tight">
            {{ headerTitle }}
          </h1>
          <p class="text-[11px] text-text-tertiary mt-0.5">
            {{ headerSubtitle }}
          </p>
        </div>

        <div class="flex items-center gap-2">
          <button
            v-if="reportsEnabled"
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
        </div>
      </header>

      <main class="flex-1 overflow-hidden flex justify-center px-4 sm:px-6">
        <div class="w-full h-full" :class="mode === 'chat' || (mode === 'task' && !selectedTask) ? 'max-w-chat' : 'max-w-2xl'">
          <ChatBox
            ref="chatBoxRef"
            :user-id="currentUserId"
            :agent-type="currentAgentType"
            :mode="mode"
            :tasks-enabled="tasksEnabled"
            @conversation-created="handleConversationCreated"
            @conversation-updated="handleConversationUpdated"
            @update:mode="handleModeChange"
          >
            <template #task-content>
              <TaskModePanel
                v-if="!selectedTask"
                :tasks="tasks"
                @select-task="handleSelectTask"
              />
              <TaskWizard
                v-else
                :task-schema="taskSchema"
                :current-step="currentStep"
                :current-step-index="currentStepIndex"
                :collected-params="collectedParams"
                :step-errors="stepErrors"
                :task-result="taskResult"
                :is-executing="isExecuting"
                :is-last-step="isLastStep"
                :is-first-step="isFirstStep"
                :progress-percent="progressPercent"
                :agent-type="currentAgentType"
                @update-param="updateParam"
                @next-step="handleNextStep"
                @prev-step="prevStep"
                @submit-task="handleSubmitTask"
                @back-to-list="handleBackToList"
              />
            </template>
          </ChatBox>
        </div>
      </main>
    </div>

    <OpsReportInbox
      :open="showOpsInbox"
      :agent-type="currentAgentType"
      @close="showOpsInbox = false"
      @unread-change="handleOpsUnreadChange"
    />
  </div>
</template>
