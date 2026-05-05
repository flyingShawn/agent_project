import { ref, computed } from 'vue'
import { fetchTasks, fetchTaskSchema, executeTask, validateTaskStep } from '../api/tasks'

const mode = ref('chat')
const tasks = ref([])
const selectedTask = ref(null)
const taskSchema = ref(null)
const currentStepIndex = ref(0)
const collectedParams = ref({})
const stepErrors = ref({})
const taskResult = ref(null)
const isExecuting = ref(false)
const isLoadingSchema = ref(false)

export function useTaskMode() {
  const currentStep = computed(() => {
    if (!taskSchema.value || !taskSchema.value.steps) return null
    return taskSchema.value.steps[currentStepIndex.value] || null
  })

  const isLastStep = computed(() => {
    if (!taskSchema.value || !taskSchema.value.steps) return false
    return currentStepIndex.value >= taskSchema.value.steps.length - 1
  })

  const isFirstStep = computed(() => currentStepIndex.value === 0)

  const progressPercent = computed(() => {
    if (!taskSchema.value || !taskSchema.value.steps) return 0
    const total = taskSchema.value.steps.length
    return Math.round(((currentStepIndex.value + 1) / total) * 100)
  })

  async function loadTasks(agentType) {
    try {
      const data = await fetchTasks(agentType)
      tasks.value = data.tasks || []
    } catch (e) {
      console.error('加载任务列表失败:', e)
      tasks.value = []
    }
  }

  async function selectTask(agentType, task) {
    selectedTask.value = task
    isLoadingSchema.value = true
    try {
      const schema = await fetchTaskSchema(agentType, task.task_id)
      taskSchema.value = schema
      currentStepIndex.value = 0
      collectedParams.value = {}
      stepErrors.value = {}
      taskResult.value = null
    } catch (e) {
      console.error('加载任务 Schema 失败:', e)
      taskSchema.value = null
    } finally {
      isLoadingSchema.value = false
    }
  }

  function updateParam(key, value) {
    collectedParams.value[key] = value
    if (stepErrors.value[key]) {
      delete stepErrors.value[key]
    }
  }

  async function validateCurrentStep(agentType) {
    if (!currentStep.value) return true

    try {
      const stepParams = {}
      for (const param of currentStep.value.params) {
        stepParams[param.key] = collectedParams.value[param.key]
      }
      const result = await validateTaskStep(
        agentType,
        selectedTask.value.task_id,
        currentStep.value.id,
        stepParams
      )
      if (!result.valid) {
        stepErrors.value = { ...stepErrors.value, ...result.errors }
        return false
      }
      return true
    } catch (e) {
      console.error('校验步骤参数失败:', e)
      return false
    }
  }

  async function nextStep(agentType) {
    const valid = await validateCurrentStep(agentType)
    if (!valid) return false

    if (currentStepIndex.value < (taskSchema.value?.steps?.length || 0) - 1) {
      currentStepIndex.value++
      stepErrors.value = {}
    }
    return true
  }

  function prevStep() {
    if (currentStepIndex.value > 0) {
      currentStepIndex.value--
      stepErrors.value = {}
    }
  }

  async function submitTask(agentType) {
    const valid = await validateCurrentStep(agentType)
    if (!valid) return

    isExecuting.value = true
    taskResult.value = null
    try {
      const result = await executeTask(agentType, selectedTask.value.task_id, collectedParams.value)
      taskResult.value = result
    } catch (e) {
      taskResult.value = {
        success: false,
        message: e.message || '任务执行失败',
        result_type: 'text',
      }
    } finally {
      isExecuting.value = false
    }
  }

  function resetTask() {
    selectedTask.value = null
    taskSchema.value = null
    currentStepIndex.value = 0
    collectedParams.value = {}
    stepErrors.value = {}
    taskResult.value = null
    isExecuting.value = false
  }

  function switchMode(newMode) {
    mode.value = newMode
    if (newMode === 'chat') {
      resetTask()
    }
  }

  function resetForAgentChange() {
    resetTask()
    tasks.value = []
    mode.value = 'chat'
  }

  return {
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
    validateCurrentStep,
    nextStep,
    prevStep,
    submitTask,
    resetTask,
    switchMode,
    resetForAgentChange,
  }
}
