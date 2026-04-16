<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: {
    type: Object,
    required: true,
  },
})

const chartRef = ref(null)
let chartInstance = null

const initChart = async () => {
  await nextTick()
  if (!chartRef.value) return

  chartInstance = echarts.init(chartRef.value)
  chartInstance.setOption(props.option)
}

const handleResize = () => {
  if (chartInstance) {
    chartInstance.resize()
  }
}

watch(
  () => props.option,
  (newOption) => {
    if (chartInstance && newOption) {
      chartInstance.setOption(newOption, true)
    }
  },
  { deep: true }
)

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)

  const observer = new ResizeObserver(() => {
    handleResize()
  })
  if (chartRef.value) {
    observer.observe(chartRef.value)
  }

  onBeforeUnmount(() => {
    observer.disconnect()
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<template>
  <div ref="chartRef" class="w-full h-[350px]"></div>
</template>
