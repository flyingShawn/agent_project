<script setup>
const props = defineProps({
  result: {
    type: Object,
    default: null,
  },
})

function getStatusIcon(status) {
  if (status === 'success') return `<svg class="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`
  if (status === 'failed') return `<svg class="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>`
  return `<svg class="w-4 h-4 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`
}
</script>

<template>
  <div v-if="result" class="task-result">
    <div
      class="flex items-center gap-3 mb-4 p-4 rounded-xl"
      :class="result.success ? 'bg-green-50' : 'bg-red-50'"
    >
      <div
        class="w-10 h-10 rounded-full flex items-center justify-center"
        :class="result.success ? 'bg-green-100' : 'bg-red-100'"
      >
        <svg v-if="result.success" class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <svg v-else class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <div>
        <h3 class="text-sm font-semibold" :class="result.success ? 'text-green-700' : 'text-red-700'">
          {{ result.success ? '执行成功' : '执行失败' }}
        </h3>
        <p class="text-xs mt-0.5" :class="result.success ? 'text-green-600' : 'text-red-600'">
          {{ result.message }}
        </p>
      </div>
    </div>

    <!-- status_list -->
    <div v-if="result.result_type === 'status_list' && result.data?.items" class="space-y-2">
      <div
        v-for="(item, idx) in result.data.items"
        :key="idx"
        class="flex items-center gap-3 px-4 py-3 bg-white border border-[#e8ecf2] rounded-xl"
      >
        <span v-html="getStatusIcon(item.status)" />
        <span class="text-sm text-text-primary flex-1">{{ item.name || item.client_name || item.label }}</span>
        <span class="text-xs text-text-tertiary">{{ item.message || item.status }}</span>
      </div>
    </div>

    <!-- table -->
    <div v-else-if="result.result_type === 'table' && result.data?.rows" class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <thead>
          <tr class="border-b border-[#e8ecf2]">
            <th
              v-for="col in (result.data.columns || [])"
              :key="col.key"
              class="text-left px-3 py-2 text-xs font-medium text-text-tertiary uppercase"
            >
              {{ col.label || col.key }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in result.data.rows" :key="idx" class="border-b border-[#e8ecf2] last:border-b-0">
            <td
              v-for="col in (result.data.columns || [])"
              :key="col.key"
              class="px-3 py-2.5 text-text-primary"
            >
              {{ row[col.key] }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- card_grid -->
    <div v-else-if="result.result_type === 'card_grid' && result.data?.items" class="grid grid-cols-2 gap-3">
      <div
        v-for="(item, idx) in result.data.items"
        :key="idx"
        class="p-3 bg-white border border-[#e8ecf2] rounded-xl"
      >
        <div class="text-sm font-medium text-text-primary">{{ item.title || item.name }}</div>
        <div class="text-xs text-text-tertiary mt-1">{{ item.description || item.value }}</div>
      </div>
    </div>

    <!-- text fallback -->
    <div v-else-if="result.data" class="p-4 bg-white border border-[#e8ecf2] rounded-xl">
      <pre class="text-xs text-text-secondary whitespace-pre-wrap break-all">{{ typeof result.data === 'string' ? result.data : JSON.stringify(result.data, null, 2) }}</pre>
    </div>
  </div>
</template>
