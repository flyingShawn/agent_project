<script setup>
const props = defineProps({
  steps: {
    type: Array,
    default: () => [],
  },
  currentStepIndex: {
    type: Number,
    default: 0,
  },
  progressPercent: {
    type: Number,
    default: 0,
  },
})
</script>

<template>
  <div class="mb-6">
    <div class="flex items-center gap-2 mb-3">
      <div
        v-for="(step, index) in steps"
        :key="step.id"
        class="flex items-center gap-2 flex-1"
      >
        <div
          class="flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold transition-all duration-300 flex-shrink-0"
          :class="{
            'bg-primary-500 text-white': index === currentStepIndex,
            'bg-primary-100 text-primary-600': index < currentStepIndex,
            'bg-gray-100 text-text-tertiary': index > currentStepIndex,
          }"
        >
          <svg v-if="index < currentStepIndex" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
          </svg>
          <span v-else>{{ index + 1 }}</span>
        </div>
        <div
          v-if="index < steps.length - 1"
          class="flex-1 h-0.5 rounded-full transition-all duration-300"
          :class="index < currentStepIndex ? 'bg-primary-300' : 'bg-gray-200'"
        />
      </div>
    </div>

    <div class="flex items-center justify-between">
      <div class="flex items-center gap-1">
        <span
          v-for="(step, index) in steps"
          :key="step.id"
          class="text-xs transition-colors duration-200"
          :class="{
            'text-primary-600 font-medium': index === currentStepIndex,
            'text-text-tertiary': index !== currentStepIndex,
          }"
        >
          {{ step.title }}
          <span v-if="index < steps.length - 1" class="mx-1.5 text-text-tertiary">·</span>
        </span>
      </div>
      <span class="text-xs text-text-tertiary">{{ progressPercent }}%</span>
    </div>
  </div>
</template>
