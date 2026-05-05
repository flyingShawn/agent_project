<script setup>
import TaskStepIndicator from './TaskStepIndicator.vue'
import TaskStepForm from './TaskStepForm.vue'
import TaskResult from './TaskResult.vue'

const props = defineProps({
  taskSchema: {
    type: Object,
    default: null,
  },
  currentStep: {
    type: Object,
    default: null,
  },
  currentStepIndex: {
    type: Number,
    default: 0,
  },
  collectedParams: {
    type: Object,
    default: () => ({}),
  },
  stepErrors: {
    type: Object,
    default: () => ({}),
  },
  taskResult: {
    type: Object,
    default: null,
  },
  isExecuting: {
    type: Boolean,
    default: false,
  },
  isLastStep: {
    type: Boolean,
    default: false,
  },
  isFirstStep: {
    type: Boolean,
    default: false,
  },
  progressPercent: {
    type: Number,
    default: 0,
  },
  agentType: {
    type: String,
    default: '',
  },
})

const emit = defineEmits([
  'update-param',
  'next-step',
  'prev-step',
  'submit-task',
  'back-to-list',
])

function handleParamUpdate(key, value) {
  emit('update-param', key, value)
}
</script>

<template>
  <div class="task-wizard h-full flex flex-col">
    <div class="flex items-center gap-3 mb-6">
      <button
        @click="emit('back-to-list')"
        class="flex items-center gap-1 text-sm text-text-tertiary hover:text-text-primary transition-colors cursor-pointer"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        返回任务列表
      </button>
      <span class="text-text-tertiary">/</span>
      <span class="text-sm font-medium text-text-primary">{{ taskSchema?.name }}</span>
    </div>

    <!-- 执行结果 -->
    <template v-if="taskResult">
      <div class="flex-1 overflow-y-auto px-1">
        <TaskResult :result="taskResult" />
      </div>
      <div class="pt-4 pb-2">
        <button
          @click="emit('back-to-list')"
          class="w-full py-2.5 px-4 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 transition-colors cursor-pointer"
        >
          返回任务列表
        </button>
      </div>
    </template>

    <!-- 步骤表单 -->
    <template v-else>
      <TaskStepIndicator
        v-if="taskSchema?.steps"
        :steps="taskSchema.steps"
        :current-step-index="currentStepIndex"
        :progress-percent="progressPercent"
      />

      <div v-if="currentStep" class="flex-1 overflow-y-auto px-1">
        <div class="mb-4">
          <h3 class="text-base font-semibold text-text-primary mb-1">{{ currentStep.title }}</h3>
          <p v-if="currentStep.description" class="text-sm text-text-tertiary">{{ currentStep.description }}</p>
        </div>

        <div class="space-y-4">
          <TaskStepForm
            v-for="param in currentStep.params"
            :key="param.key"
            :param="param"
            :model-value="collectedParams[param.key]"
            :error="stepErrors[param.key] || ''"
            :agent-type="agentType"
            @update:model-value="handleParamUpdate(param.key, $event)"
          />
        </div>
      </div>

      <div class="pt-4 pb-2 flex items-center gap-3">
        <button
          v-if="!isFirstStep"
          @click="emit('prev-step')"
          class="flex-1 py-2.5 px-4 border border-[#e8ecf2] text-text-secondary rounded-xl text-sm font-medium hover:bg-surface-hover transition-colors cursor-pointer"
        >
          上一步
        </button>
        <button
          v-if="!isLastStep"
          @click="emit('next-step')"
          class="flex-1 py-2.5 px-4 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 transition-colors cursor-pointer"
        :class="{ 'opacity-50 cursor-not-allowed': isExecuting }"
        >
          下一步
        </button>
        <button
          v-if="isLastStep"
          @click="emit('submit-task')"
          :disabled="isExecuting"
          class="flex-1 py-2.5 px-4 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer flex items-center justify-center gap-2"
        >
          <svg v-if="isExecuting" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          {{ isExecuting ? '执行中...' : '提交任务' }}
        </button>
      </div>
    </template>
  </div>
</template>
