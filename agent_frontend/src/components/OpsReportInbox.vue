<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import { marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import {
  getLatestOpsReport,
  getOpsReport,
  listOpsReports,
  markOpsReportRead,
} from '../api/opsReports'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close', 'unread-change'])

marked.use(
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = hljs.getLanguage(lang) ? lang : 'plaintext'
      return hljs.highlight(code, { language }).value
    },
  })
)
marked.use({ breaks: true, gfm: true })

const reports = ref([])
const selectedReportId = ref(null)
const selectedReport = ref(null)
const renderedHtml = ref('')
const isLoadingList = ref(false)
const isLoadingDetail = ref(false)
const listError = ref('')
const detailError = ref('')
let pollTimer = null

function severityClass(severity) {
  const mapping = {
    normal: 'bg-emerald-50 text-emerald-700',
    attention: 'bg-amber-50 text-amber-700',
    warning: 'bg-rose-50 text-rose-700',
  }
  return mapping[severity] || 'bg-slate-100 text-slate-700'
}

function severityLabel(severity) {
  const mapping = {
    normal: '正常',
    attention: '关注',
    warning: '预警',
  }
  return mapping[severity] || '未知'
}

function formatDateTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { hour12: false })
}

function renderMarkdown(content) {
  if (!content) {
    renderedHtml.value = ''
    return
  }
  renderedHtml.value = DOMPurify.sanitize(marked.parse(content))
}

async function refreshUnreadMeta() {
  try {
    const payload = await getLatestOpsReport()
    emit('unread-change', payload?.unread_total || 0)
  } catch (_) {
    // 轮询失败时不打断界面
  }
}

async function loadReports(preferredId = null) {
  isLoadingList.value = true
  listError.value = ''

  try {
    const payload = await listOpsReports({ limit: 20 })
    reports.value = payload.reports || []
    emit('unread-change', payload.unread_total || 0)

    const currentSelectedExists = reports.value.some((item) => item.report_id === selectedReportId.value)
    const nextId =
      preferredId ||
      (currentSelectedExists ? selectedReportId.value : null) ||
      reports.value[0]?.report_id ||
      null

    if (nextId) {
      await loadReport(nextId)
    } else {
      selectedReportId.value = null
      selectedReport.value = null
      renderMarkdown('')
    }
  } catch (error) {
    listError.value = error.message || '加载运维简报失败'
  } finally {
    isLoadingList.value = false
  }
}

async function loadReport(reportId) {
  if (!reportId) return

  isLoadingDetail.value = true
  detailError.value = ''

  try {
    const payload = await getOpsReport(reportId)
    selectedReportId.value = reportId
    selectedReport.value = payload
    renderMarkdown(payload.content_md || '')

    if (payload.unread) {
      const readResult = await markOpsReportRead(reportId)
      selectedReport.value = { ...payload, unread: false }
      reports.value = reports.value.map((item) =>
        item.report_id === reportId ? { ...item, unread: false } : item
      )
      emit('unread-change', readResult?.unread_total || 0)
    }
  } catch (error) {
    detailError.value = error.message || '加载简报详情失败'
  } finally {
    isLoadingDetail.value = false
  }
}

function startPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
  pollTimer = setInterval(async () => {
    if (props.open) {
      await loadReports(selectedReportId.value)
    } else {
      await refreshUnreadMeta()
    }
  }, 60000)
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      await loadReports()
    } else {
      await refreshUnreadMeta()
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await refreshUnreadMeta()
  startPolling()
})

onBeforeUnmount(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 bg-black/20"
    @click.self="emit('close')"
  >
    <div class="absolute inset-y-0 right-0 w-full max-w-[980px] bg-white border-l border-[#e8ecf2] shadow-2xl flex">
      <aside class="w-[320px] border-r border-[#e8ecf2] flex flex-col bg-[#fafbfc]">
        <div class="px-4 py-3 border-b border-[#e8ecf2] flex items-center justify-between">
          <div>
            <h2 class="text-sm font-semibold text-text-primary">运维简报</h2>
            <p class="text-[12px] text-text-tertiary mt-0.5">最近生成的巡检摘要</p>
          </div>
          <button
            @click="emit('close')"
            class="p-1.5 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded-md transition-colors cursor-pointer"
            title="关闭"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto no-scrollbar">
          <div v-if="isLoadingList && reports.length === 0" class="px-4 py-6 text-sm text-text-tertiary">
            正在加载简报...
          </div>
          <div v-else-if="listError" class="px-4 py-6 text-sm text-rose-600">
            {{ listError }}
          </div>
          <div v-else-if="reports.length === 0" class="px-4 py-6 text-sm text-text-tertiary">
            暂无运维简报
          </div>
          <button
            v-for="report in reports"
            :key="report.report_id"
            @click="loadReport(report.report_id)"
            class="w-full text-left px-4 py-3 border-b border-[#eef1f5] hover:bg-white transition-colors cursor-pointer"
            :class="report.report_id === selectedReportId ? 'bg-white' : ''"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-text-primary truncate">{{ report.title }}</span>
                  <span v-if="report.unread" class="w-2 h-2 rounded-full bg-rose-500 flex-shrink-0"></span>
                </div>
                <p class="text-[12px] text-text-tertiary mt-1">{{ formatDateTime(report.generated_at) }}</p>
              </div>
              <span
                class="text-[11px] px-2 py-0.5 rounded-md font-medium flex-shrink-0"
                :class="severityClass(report.severity)"
              >
                {{ severityLabel(report.severity) }}
              </span>
            </div>
            <p class="text-[12px] text-text-secondary mt-2 leading-5 max-h-[72px] overflow-hidden">
              {{ report.summary }}
            </p>
          </button>
        </div>
      </aside>

      <section class="flex-1 min-w-0 flex flex-col">
        <div class="px-5 py-4 border-b border-[#e8ecf2]">
          <div v-if="selectedReport" class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <h3 class="text-base font-semibold text-text-primary truncate">{{ selectedReport.title }}</h3>
                <span
                  class="text-[11px] px-2 py-0.5 rounded-md font-medium flex-shrink-0"
                  :class="severityClass(selectedReport.severity)"
                >
                  {{ severityLabel(selectedReport.severity) }}
                </span>
              </div>
              <p class="text-[12px] text-text-tertiary mt-1">
                生成时间：{{ formatDateTime(selectedReport.generated_at) }}
              </p>
            </div>
          </div>
          <div v-else class="text-sm text-text-tertiary">
            请选择一份运维简报查看详情
          </div>
        </div>

        <div class="flex-1 overflow-y-auto no-scrollbar px-5 py-4">
          <div v-if="isLoadingDetail" class="text-sm text-text-tertiary">正在加载详情...</div>
          <div v-else-if="detailError" class="text-sm text-rose-600">{{ detailError }}</div>
          <div v-else-if="selectedReport" class="space-y-4">
            <div class="bg-[#fafbfc] border border-[#e8ecf2] rounded-lg px-4 py-3">
              <p class="text-sm text-text-secondary whitespace-pre-line leading-6">{{ selectedReport.summary }}</p>
            </div>
            <div class="message-content max-w-none text-text-primary" v-html="renderedHtml"></div>
          </div>
          <div v-else class="text-sm text-text-tertiary">
            暂无可展示内容
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
