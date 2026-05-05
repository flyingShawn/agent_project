<script setup>
import TaskCard from './TaskCard.vue'

const props = defineProps({
  tasks: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['select-task'])
</script>

<template>
  <div class="h-full flex flex-col items-center justify-center px-6 pb-24">
    <div class="text-center mb-8">
      <div class="w-14 h-14 rounded-2xl bg-primary-50 text-primary-500 flex items-center justify-center mx-auto mb-4">
        <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
        </svg>
      </div>
      <h2 class="text-2xl font-semibold text-text-primary mb-2">选择要执行的任务</h2>
      <p class="text-sm text-text-tertiary">选择一个任务，按步骤填写参数后提交执行</p>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 max-w-2xl w-full">
      <TaskCard
        v-for="task in tasks"
        :key="task.task_id"
        :task="task"
        @select="emit('select-task', $event)"
      />
    </div>
  </div>
</template>
