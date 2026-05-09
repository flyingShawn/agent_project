<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import { marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import {
  listOpsReports,
  getOpsReport,
  markOpsReportRead,
  getOpsDefinitions,
  updateOpsDefinition,
  runOpsReportNow,
} from './api/opsReports'

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

const route = useRoute()
const agentType = computed(() => route.params.agentType || 'desk-agent')

const timeRanges = [
  { label: '近3天', value: 'last_3_days' },
  { label: '近7天', value: 'last_7_days' },
  { label: '近30天', value: 'last_30_days' },
  { label: '本周', value: 'this_week' },
  { label: '本月', value: 'this_month' },
]

const scheduleTypes = [
  { label: '每日', value: 'daily' },
  { label: '每周', value: 'weekly' },
]

const weekDays = [
  { label: '一', value: 1 }, { label: '二', value: 2 }, { label: '三', value: 3 },
  { label: '四', value: 4 }, { label: '五', value: 5 }, { label: '六', value: 6 },
  { label: '日', value: 7 },
]

const allModules = [
  { key: 'online_status', title: '在线状态', category: 'realtime', description: '在线终端、在线率、未开机', alwaysData: true, icon: 'online' },
  { key: 'server_health', title: '服务器运行', category: 'realtime', description: 'CPU、内存、磁盘占用率', alwaysData: false, icon: 'server' },
  { key: 'remote_top', title: '远程协助排行', category: 'period', description: '高频远程协助终端', alwaysData: false, range: 'last_3_days', icon: 'remote' },
  { key: 'usb_top', title: 'U盘使用排行', category: 'period', description: 'U盘设备Top + 电脑Top', alwaysData: false, range: 'last_7_days', icon: 'usb' },
  { key: 'wallpaper_screen', title: '壁纸屏保策略', category: 'realtime', description: '策略应用情况', alwaysData: false, icon: 'wallpaper' },
  { key: 'file_distribution', title: '文件分发统计', category: 'period', description: '分发任务量与执行情况', alwaysData: false, range: 'last_7_days', icon: 'file' },
  { key: 'antivirus', title: '杀毒软件安装', category: 'realtime', description: '安装数量与品牌分布', alwaysData: true, icon: 'antivirus' },
  { key: 'hardware_change', title: '硬件资产变化', category: 'period', description: '新增、变更、减少资产', alwaysData: true, range: 'last_7_days', icon: 'hardware' },
]

const moduleIconMap = {
  online: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  server: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
  remote: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  usb: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="m4.93 10.93 1.41 1.41"/><path d="M2 18h2"/><path d="M20 18h2"/><path d="m19.07 10.93-1.41 1.41"/><path d="M22 22H2"/><path d="m16 6-4-4-4 4"/><path d="m16 18-4 4-4-4"/></svg>`,
  wallpaper: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
  file: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>`,
  antivirus: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>`,
  hardware: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`,
}

const severityMap = {
  normal: { label: '正常', color: '#22C55E', bg: 'rgba(34,197,94,0.12)', lightBg: 'rgba(34,197,94,0.08)', lightColor: '#16a34a' },
  attention: { label: '关注', color: '#F59E0B', bg: 'rgba(245,158,11,0.12)', lightBg: 'rgba(245,158,11,0.08)', lightColor: '#d97706' },
  warning: { label: '告警', color: '#EF4444', bg: 'rgba(239,68,68,0.12)', lightBg: 'rgba(239,68,68,0.08)', lightColor: '#dc2626' },
}

const mainView = ref('report')
const activeHistoryKey = ref(null)
const configTemplateKey = ref(null)
const viewMode = ref('visual')
const themeMode = ref('dark')
const currentTime = ref(new Date())
const scheduleType = ref('daily')
const scheduleTime = ref('08:00')
const weekDay = ref(1)

const definitions = ref([])
const reports = ref([])
const selectedReport = ref(null)
const renderedHtml = ref('')
const isLoadingDefs = ref(false)
const isLoadingReports = ref(false)
const isLoadingDetail = ref(false)
const isGenerating = ref(false)
const isSavingDef = ref(false)

const configTemplate = computed(() => definitions.value.find((d) => d.report_key === configTemplateKey.value) || {})

const configModuleState = computed(() => {
  const def = configTemplate.value
  if (!def || !def.modules) return {}
  const state = {}
  for (const m of def.modules) {
    state[m.key] = m.enabled
  }
  return state
})

const configEnabledCount = computed(() => {
  const enabled = Object.values(configModuleState.value).filter(Boolean).length
  return `${enabled}/${allModules.length}`
})

const isConfigTemplateEnabled = computed(() => configTemplate.value?.enabled ?? true)

const isDark = computed(() => themeMode.value === 'dark')

const selectedReportSnapshot = computed(() => selectedReport.value?.snapshot || {})

const selectedReportModules = computed(() => {
  const snap = selectedReportSnapshot.value
  if (!snap || Object.keys(snap).length === 0) return []
  return allModules.filter((m) => snap[m.key])
})

const selectedReportDef = computed(() => {
  if (!selectedReport.value) return null
  return definitions.value.find((d) => d.report_key === selectedReport.value.report_key) || null
})

const timeStr = computed(() => {
  const d = currentTime.value
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
})

const dateStr = computed(() => {
  const d = currentTime.value
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} 周${weekdays[d.getDay()]}`
})

function formatTimestamp(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('zh-CN', { hour12: false })
}

function getModuleIcon(iconKey) {
  return moduleIconMap[iconKey] || ''
}

function getModuleRange(key) {
  const def = configTemplate.value
  if (!def || !def.modules) return 'last_7_days'
  const m = def.modules.find((mod) => mod.key === key)
  return m?.range || 'last_7_days'
}

function isWeeklyTemplate() {
  return scheduleType.value === 'weekly'
}

function normalizeModulesForSave(modules) {
  return (modules || []).map((module) => {
    if (isWeeklyTemplate() && module.type === 'period') {
      return { ...module, range: 'last_week' }
    }
    return module
  })
}

function ratioWidth(item) {
  const applied = Number(item?.applied || 0)
  const total = Number(item?.total || 0)
  if (total <= 0) return '0%'
  return `${Math.min(100, Math.max(0, (applied / total) * 100))}%`
}

function selectTemplate(key) {
  configTemplateKey.value = key
  mainView.value = 'config'
  const def = definitions.value.find((d) => d.report_key === key)
  if (def?.schedule) {
    scheduleType.value = def.schedule.type || 'daily'
    scheduleTime.value = def.schedule.time || '08:00'
    weekDay.value = def.schedule.weekday || 1
  }
}

function selectHistory(reportId) {
  loadReportDetail(reportId)
}

async function toggleConfigModule(key) {
  const def = configTemplate.value
  if (!def || !def.modules) return
  const m = def.modules.find((mod) => mod.key === key)
  if (m) {
    m.enabled = !m.enabled
    await saveDefinition()
  }
}

async function toggleTemplateEnabled() {
  const def = configTemplate.value
  if (!def) return
  def.enabled = !def.enabled
  await saveDefinition()
}

async function updateModuleRange(key, range) {
  const def = configTemplate.value
  if (!def || !def.modules) return
  const m = def.modules.find((mod) => mod.key === key)
  if (m) {
    m.range = isWeeklyTemplate() ? 'last_week' : range
    await saveDefinition()
  }
}

async function setScheduleType(value) {
  scheduleType.value = value
  if (value === 'weekly') {
    for (const module of (configTemplate.value?.modules || [])) {
      if (module.type === 'period') module.range = 'last_week'
    }
  }
  await saveDefinition()
}

async function setWeekDay(value) {
  weekDay.value = value
  await saveDefinition()
}

async function saveDefinition() {
  const def = configTemplate.value
  if (!def || !def.report_key) return
  isSavingDef.value = true
  try {
    await updateOpsDefinition(agentType.value, def.report_key, {
      enabled: def.enabled,
      schedule: { type: scheduleType.value, time: scheduleTime.value, weekday: weekDay.value },
      modules: normalizeModulesForSave(def.modules),
    })
    await loadDefinitions()
  } catch (e) {
    console.error('保存简报定义失败:', e)
  } finally {
    isSavingDef.value = false
  }
}

async function generateNow() {
  const reportKey = configTemplate.value?.report_key || selectedReport.value?.report_key
  if (!reportKey) return
  isGenerating.value = true
  try {
    const generated = await runOpsReportNow(agentType.value, reportKey)
    await loadReports()
    if (generated?.report_id) {
      await loadReportDetail(generated.report_id)
    }
  } catch (e) {
    console.error('生成简报失败:', e)
  } finally {
    isGenerating.value = false
  }
}

async function loadDefinitions() {
  isLoadingDefs.value = true
  try {
    const payload = await getOpsDefinitions(agentType.value)
    definitions.value = payload.definitions || []
  } catch (e) {
    console.error('加载简报定义失败:', e)
    definitions.value = []
  } finally {
    isLoadingDefs.value = false
  }
}

async function loadReports() {
  isLoadingReports.value = true
  try {
    const payload = await listOpsReports(agentType.value, { limit: 20 })
    reports.value = payload.reports || []
    if (reports.value.length > 0 && !selectedReport.value) {
      await loadReportDetail(reports.value[0].report_id)
    }
  } catch (e) {
    console.error('加载简报列表失败:', e)
    reports.value = []
  } finally {
    isLoadingReports.value = false
  }
}

async function loadReportDetail(reportId) {
  isLoadingDetail.value = true
  try {
    const payload = await getOpsReport(agentType.value, reportId)
    selectedReport.value = payload
    activeHistoryKey.value = reportId
    mainView.value = 'report'
    if (payload.unread) {
      try {
        await markOpsReportRead(agentType.value, reportId)
        selectedReport.value = { ...payload, unread: false }
        reports.value = reports.value.map((item) => (
          item.report_id === reportId ? { ...item, unread: false } : item
        ))
      } catch (e) {
        console.error('标记简报已读失败:', e)
      }
    }
    if (payload.content_md) {
      renderedHtml.value = DOMPurify.sanitize(marked.parse(payload.content_md))
    } else {
      renderedHtml.value = ''
    }
  } catch (e) {
    console.error('加载简报详情失败:', e)
  } finally {
    isLoadingDetail.value = false
  }
}

const chartRefs = ref({})
const chartInstances = ref({})

const textColor = computed(() => isDark.value ? '#94A3B8' : '#64748B')
const axisLineColor = computed(() => isDark.value ? '#334155' : '#E2E8F0')
const splitLineColor = computed(() => isDark.value ? '#1E293B' : '#F1F5F9')
const labelColor = computed(() => isDark.value ? '#CBD5E1' : '#475569')
const tooltipBg = computed(() => isDark.value ? 'rgba(15,23,42,0.9)' : 'rgba(255,255,255,0.95)')
const tooltipBorder = computed(() => isDark.value ? '#334155' : '#E2E8F0')
const tooltipText = computed(() => isDark.value ? '#F8FAFC' : '#1E293B')

function buildChartOption(moduleKey, snapshot) {
  if (!snapshot) return null
  const base = { backgroundColor: 'transparent', tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } } }
  const grid = { top: 30, right: 16, bottom: 24, left: 44 }
  const gridHorizontal = { top: 12, right: 40, bottom: 12, left: 120 }

  switch (moduleKey) {
    case 'online_status': {
      const d = snapshot
      return {
        ...base, grid,
        xAxis: { type: 'category', data: ['在线', '离线', '未开机'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: textColor.value } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value } },
        series: [{ type: 'bar', data: [{ value: d.online_count, itemStyle: { color: '#22C55E' } }, { value: d.total_count - d.online_count - (d.not_booted_count || 0), itemStyle: { color: '#F59E0B' } }, { value: d.not_booted_count || 0, itemStyle: { color: '#EF4444' } }], barWidth: 40, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
      }
    }
    case 'server_health': {
      const servers = snapshot.servers || []
      return {
        ...base, grid, legend: { data: ['CPU', '内存', '磁盘'], textStyle: { color: textColor.value, fontSize: 11 }, top: 4, right: 16 },
        xAxis: { type: 'category', data: servers.map((s) => s.name), axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: textColor.value } },
        yAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, formatter: '{value}%' } },
        series: [
          { name: 'CPU', type: 'bar', data: servers.map((s) => s.cpu), itemStyle: { color: '#00D4FF', borderRadius: [3, 3, 0, 0] }, barWidth: 12 },
          { name: '内存', type: 'bar', data: servers.map((s) => s.memory), itemStyle: { color: '#A855F7', borderRadius: [3, 3, 0, 0] }, barWidth: 12 },
          { name: '磁盘', type: 'bar', data: servers.map((s) => s.disk), itemStyle: { color: '#F59E0B', borderRadius: [3, 3, 0, 0] }, barWidth: 12 },
        ],
      }
    }
    case 'remote_top': {
      const clients = (snapshot.top_clients || []).slice(0, 5).reverse()
      return {
        ...base, grid: gridHorizontal,
        xAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value } },
        yAxis: { type: 'category', data: clients.map((c) => c.machine_name || c.ip || '未知'), axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: labelColor.value, fontSize: 11 } },
        series: [{ type: 'bar', data: clients.map((c) => c.remote_count), itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#00D4FF' }, { offset: 1, color: '#22C55E' }]), borderRadius: [0, 4, 4, 0] }, barWidth: 16 }],
      }
    }
    case 'usb_top': {
      const devices = (snapshot.top_devices || []).slice(0, 5).reverse()
      return {
        ...base, grid: { ...gridHorizontal, left: 140 },
        xAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value } },
        yAxis: { type: 'category', data: devices.map((d) => d.device_name || '未知'), axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: labelColor.value, fontSize: 11 } },
        series: [{ type: 'bar', data: devices.map((d) => d.usage_count), itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#A855F7' }, { offset: 1, color: '#EC4899' }]), borderRadius: [0, 4, 4, 0] }, barWidth: 16 }],
      }
    }
    case 'antivirus': {
      const items = snapshot.items || []
      return {
        ...base,
        series: [{
          type: 'pie', radius: ['52%', '78%'], center: ['50%', '50%'], avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: isDark.value ? '#0F172A' : '#FFFFFF', borderWidth: 2 },
          label: { show: true, position: 'outside', color: labelColor.value, fontSize: 11, formatter: '{b}\n{d}%' },
          labelLine: { lineStyle: { color: isDark.value ? '#475569' : '#CBD5E1' } },
          data: items.map((item, i) => ({
            value: item.count || item.percent, name: item.name,
            itemStyle: { color: ['#22C55E', '#00D4FF', '#A855F7', '#F59E0B', '#EF4444'][i % 5] },
          })),
        }],
      }
    }
    case 'hardware_change': {
      return {
        ...base, grid,
        xAxis: { type: 'category', data: ['新增', '变更', '减少', '待确认'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: textColor.value } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value } },
        series: [{ type: 'bar', data: [
          { value: snapshot.added || 0, itemStyle: { color: '#22C55E' } },
          { value: snapshot.changed || 0, itemStyle: { color: '#00D4FF' } },
          { value: snapshot.removed || 0, itemStyle: { color: '#EF4444' } },
          { value: snapshot.pending_confirm || 0, itemStyle: { color: '#F59E0B' } },
        ], barWidth: 40, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
      }
    }
    default:
      return null
  }
}

function setChartRef(el, key) {
  if (el) chartRefs.value[key] = el
}

function initCharts() {
  if (mainView.value !== 'report' || viewMode.value !== 'visual') return
  Object.values(chartInstances.value).forEach((inst) => { if (inst) inst.dispose() })
  chartInstances.value = {}

  const snap = selectedReportSnapshot.value
  if (!snap) return

  nextTick(() => {
    for (const moduleKey of Object.keys(snap)) {
      const option = buildChartOption(moduleKey, snap[moduleKey])
      if (!option) continue
      const el = chartRefs.value[moduleKey]
      if (!el) continue
      const instance = echarts.init(el, null, { renderer: 'canvas' })
      instance.setOption(option)
      chartInstances.value[moduleKey] = instance
    }
  })
}

function handleResize() {
  Object.values(chartInstances.value).forEach((inst) => { if (inst) inst.resize() })
}

let timer = null
onMounted(async () => {
  await loadDefinitions()
  await loadReports()
  window.addEventListener('resize', handleResize)
  timer = setInterval(() => { currentTime.value = new Date() }, 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  Object.values(chartInstances.value).forEach((inst) => { if (inst) inst.dispose() })
  if (timer) clearInterval(timer)
})

watch([viewMode, themeMode, mainView, selectedReport], () => {
  chartRefs.value = {}
  nextTick(() => initCharts())
}, { deep: true })
</script>

<template>
  <main class="ops-dashboard" :class="{ light: !isDark }">
    <header class="dash-header">
      <div class="header-left">
        <div class="logo-mark">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <rect x="2" y="2" width="24" height="24" rx="6" stroke="#00D4FF" stroke-width="1.5" fill="none" opacity="0.6"/>
            <rect x="6" y="6" width="16" height="16" rx="3" stroke="#22C55E" stroke-width="1.5" fill="none"/>
            <circle cx="14" cy="14" r="4" fill="#00D4FF" opacity="0.8"/>
          </svg>
        </div>
        <div>
          <h1>运维简报中心</h1>
          <p class="header-sub">Operations Briefing Center</p>
        </div>
      </div>
      <div class="header-center">
        <div class="live-badge"><span class="pulse-dot"></span><span>LIVE</span></div>
        <div class="header-time">
          <span class="time-value">{{ timeStr }}</span>
          <span class="date-value">{{ dateStr }}</span>
        </div>
      </div>
      <div class="header-right">
        <div class="mode-switch-group">
          <button class="mode-btn" :class="{ active: viewMode === 'text' }" type="button" @click="viewMode = 'text'" title="文字版">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
          <button class="mode-btn" :class="{ active: viewMode === 'visual' }" type="button" @click="viewMode = 'visual'" title="可视化版">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          </button>
          <span class="mode-divider"></span>
          <button class="mode-btn" :class="{ active: themeMode === 'dark' }" type="button" @click="themeMode = 'dark'" title="深色">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          </button>
          <button class="mode-btn" :class="{ active: themeMode === 'light' }" type="button" @click="themeMode = 'light'" title="浅色">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
          </button>
        </div>
      </div>
    </header>

    <div class="dash-body">
      <aside class="sidebar-left">
        <section class="sidebar-section">
          <div class="section-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <h2>简报模板</h2>
          </div>
          <div v-if="isLoadingDefs" class="loading-hint">加载中...</div>
          <div v-else class="template-list">
            <button v-for="def in definitions" :key="def.report_key" class="template-item" :class="{ active: mainView === 'config' && configTemplateKey === def.report_key }" type="button" @click="selectTemplate(def.report_key)">
              <div class="template-icon" :class="def.schedule?.type === 'weekly' ? 'weekly' : 'daily'">
                <svg v-if="def.schedule?.type !== 'weekly'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              </div>
              <div class="template-info">
                <strong>{{ def.name }}</strong>
                <small>{{ def.schedule?.type === 'weekly' ? '每周' : '每日' }} {{ def.schedule?.time || '08:00' }}</small>
              </div>
              <span class="template-status" :class="def.enabled ? 'active' : 'inactive'">{{ def.enabled ? '启用' : '停用' }}</span>
            </button>
          </div>
        </section>

        <section class="sidebar-section history-section">
          <div class="section-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <h2>历史简报</h2>
            <span class="count-badge">{{ reports.length }}</span>
          </div>
          <div v-if="isLoadingReports && reports.length === 0" class="loading-hint">加载中...</div>
          <div v-else-if="reports.length === 0" class="loading-hint">暂无简报</div>
          <div v-else class="history-list">
            <button v-for="report in reports" :key="report.report_id" class="history-item" :class="{ active: mainView === 'report' && activeHistoryKey === report.report_id }" type="button" @click="selectHistory(report.report_id)">
              <div class="history-severity" :style="{ background: severityMap[report.severity]?.color || '#94A3B8' }"></div>
              <div class="history-info">
                <strong><span v-if="report.unread" class="unread-dot"></span>{{ report.title }}</strong>
                <span>{{ formatTimestamp(report.generated_at) }}</span>
              </div>
            </button>
          </div>
        </section>
      </aside>

      <main class="main-content">
        <!-- 配置视图 -->
        <div v-if="mainView === 'config'" class="config-view">
          <div class="config-banner">
            <div class="config-banner-bg"></div>
            <div class="config-banner-content">
              <div class="config-banner-left">
                <div class="config-banner-icon" :class="configTemplate.schedule?.type === 'weekly' ? 'weekly' : 'daily'">
                  <svg v-if="configTemplate.schedule?.type !== 'weekly'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                </div>
                <div>
                  <h2>{{ configTemplate.name || '简报配置' }}</h2>
                  <p>配置此简报的生成计划和展示模块</p>
                </div>
              </div>
              <div class="config-actions">
                <div class="enable-row">
                  <span class="enable-label">启用</span>
                  <button class="toggle-switch lg" :class="{ on: isConfigTemplateEnabled }" type="button" @click="toggleTemplateEnabled">
                    <span class="toggle-knob"></span>
                  </button>
                </div>
                <button class="btn-primary" :disabled="isGenerating" type="button" @click="generateNow">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  {{ isGenerating ? '生成中...' : '立即生成' }}
                </button>
              </div>
            </div>
          </div>

          <div class="config-body">
            <section class="config-card schedule-card">
              <div class="config-card-header">
                <div class="config-card-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  <h3>生成计划</h3>
                </div>
              </div>
              <div class="schedule-config">
                <div class="schedule-row">
                  <span class="schedule-label">生成频率</span>
                  <div class="schedule-type-row">
                    <button v-for="st in scheduleTypes" :key="st.value" class="sch-btn" :class="{ active: scheduleType === st.value }" type="button" @click="setScheduleType(st.value)">{{ st.label }}</button>
                  </div>
                </div>
                <div class="schedule-row">
                  <span class="schedule-label">生成时间</span>
                  <input v-model="scheduleTime" type="time" class="field-input" @change="saveDefinition" />
                </div>
                <div v-if="scheduleType === 'weekly'" class="schedule-row">
                  <span class="schedule-label">生成日</span>
                  <div class="week-day-row">
                    <button v-for="wd in weekDays" :key="wd.value" class="week-day-btn" :class="{ active: weekDay === wd.value }" type="button" @click="setWeekDay(wd.value)">{{ wd.label }}</button>
                  </div>
                </div>
              </div>
            </section>

            <section class="config-card modules-card">
              <div class="config-card-header">
                <div class="config-card-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                  <h3>展示模块</h3>
                  <span class="enabled-count">{{ configEnabledCount }} 已启用</span>
                </div>
              </div>
              <div class="module-grid">
                <article v-for="m in allModules" :key="m.key" class="module-card" :class="{ disabled: !configModuleState[m.key], [m.category]: true }">
                  <div class="module-card-header">
                    <div class="module-icon-wrap" :class="{ on: configModuleState[m.key] }" v-html="getModuleIcon(m.icon)"></div>
                    <div class="module-card-info">
                      <div class="module-title-row">
                        <strong>{{ m.title }}</strong>
                        <span v-if="m.alwaysData" class="data-tag always">必选</span>
                        <span v-else class="data-tag optional">可选</span>
                      </div>
                      <p>{{ m.description }}</p>
                    </div>
                    <button class="toggle-switch" :class="{ on: configModuleState[m.key] }" type="button" @click="toggleConfigModule(m.key)">
                      <span class="toggle-knob"></span>
                    </button>
                  </div>
                  <div v-if="m.category === 'period' && configModuleState[m.key] && !isWeeklyTemplate()" class="module-range">
                    <span class="range-label">统计周期</span>
                    <div class="range-btns">
                      <button v-for="range in timeRanges" :key="range.value" class="range-btn" :class="{ active: getModuleRange(m.key) === range.value }" type="button" @click="updateModuleRange(m.key, range.value)">{{ range.label }}</button>
                    </div>
                  </div>
                  <div v-else-if="m.category === 'period' && configModuleState[m.key] && isWeeklyTemplate()" class="module-realtime">
                    <span class="pulse-dot-sm"></span>
                    <span>周报固定统计上一自然周</span>
                  </div>
                  <div v-else-if="m.category === 'realtime' && configModuleState[m.key]" class="module-realtime">
                    <span class="pulse-dot-sm"></span>
                    <span>实时数据，无需配置周期</span>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </div>

        <!-- 简报内容视图 -->
        <template v-if="mainView === 'report'">
          <div v-if="isLoadingDetail" class="loading-center">加载简报详情...</div>
          <div v-else-if="!selectedReport" class="empty-center">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity="0.3"><rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" stroke-width="1.5"/><line x1="14" y1="20" x2="28" y2="20" stroke="currentColor" stroke-width="1.5"/><line x1="14" y1="26" x2="22" y2="26" stroke="currentColor" stroke-width="1.5"/></svg>
            <p>请从左侧选择一条历史简报查看</p>
          </div>
          <template v-else>
            <div class="report-meta">
              <div>
                <div class="meta-tags">
                  <span class="meta-tag">{{ selectedReport.title }}</span>
                  <span class="meta-tag severity" :style="{ background: isDark ? severityMap[selectedReport.severity]?.bg : severityMap[selectedReport.severity]?.lightBg, color: isDark ? severityMap[selectedReport.severity]?.color : severityMap[selectedReport.severity]?.lightColor }">
                    {{ severityMap[selectedReport.severity]?.label || '未知' }}
                  </span>
                </div>
                <p class="report-summary">{{ selectedReport.summary }}</p>
                <p class="report-time">生成时间：{{ formatTimestamp(selectedReport.generated_at) }}</p>
              </div>
              <button class="gen-btn" :disabled="isGenerating" type="button" @click="generateNow">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                {{ isGenerating ? '生成中...' : '立即生成' }}
              </button>
            </div>

            <div v-if="viewMode === 'visual'" class="chart-grid">
              <article v-for="m in selectedReportModules" :key="m.key" class="chart-card" :class="{ 'span-2': ['online_status', 'server_health', 'hardware_change'].includes(m.key) }">
                <div class="chart-title">{{ m.title }}</div>
                <div :ref="(el) => setChartRef(el, m.key)" class="chart-container"></div>
              </article>

              <article v-if="selectedReportSnapshot.wallpaper_screen" class="chart-card span-2">
                <div class="chart-title">壁纸屏保策略应用情况</div>
                <div class="wallpaper-rows">
                  <div class="wallpaper-row">
                    <div class="wallpaper-info">
                      <strong>壁纸策略</strong>
                      <span>已应用 {{ selectedReportSnapshot.wallpaper_screen.wallpaper?.applied || 0 }}/{{ selectedReportSnapshot.wallpaper_screen.wallpaper?.total || 0 }}</span>
                    </div>
                    <div class="wallpaper-bar"><div class="wallpaper-bar-fill" :style="{ width: ratioWidth(selectedReportSnapshot.wallpaper_screen.wallpaper) }"></div></div>
                  </div>
                  <div class="wallpaper-row">
                    <div class="wallpaper-info">
                      <strong>屏保策略</strong>
                      <span>已应用 {{ selectedReportSnapshot.wallpaper_screen.screensaver?.applied || 0 }}/{{ selectedReportSnapshot.wallpaper_screen.screensaver?.total || 0 }}</span>
                    </div>
                    <div class="wallpaper-bar"><div class="wallpaper-bar-fill" :style="{ width: ratioWidth(selectedReportSnapshot.wallpaper_screen.screensaver) }"></div></div>
                  </div>
                </div>
              </article>

              <article v-if="selectedReportSnapshot.file_distribution" class="chart-card span-2">
                <div class="chart-title">文件分发任务</div>
                <div class="file-dist-rows">
                  <div v-for="task in (selectedReportSnapshot.file_distribution.tasks || [])" :key="task.task_name" class="file-dist-row">
                    <div class="file-dist-name">{{ task.task_name }}</div>
                    <div class="file-dist-stats">
                      <span class="stat-item dist"><strong>{{ task.distributed }}</strong>分发</span>
                      <span class="stat-item success"><strong>{{ task.success }}</strong>成功</span>
                      <span class="stat-item failed"><strong>{{ task.failed }}</strong>失败</span>
                      <span class="stat-item exec"><strong>{{ task.exec_success }}</strong>执行成功</span>
                    </div>
                  </div>
                </div>
              </article>
            </div>

            <article v-if="viewMode === 'text'" class="text-report panel">
              <div class="message-content max-w-none text-text-primary" v-html="renderedHtml"></div>
            </article>
          </template>
        </template>
      </main>
    </div>
  </main>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

.ops-dashboard {
  --bg-deep: #0A0E1A; --bg-base: #0F172A; --bg-card: #1E293B; --bg-card-hover: #263548;
  --border: #334155; --border-light: rgba(51,65,85,0.5);
  --text-primary: #F8FAFC; --text-secondary: #CBD5E1; --text-muted: #94A3B8;
  --accent-cyan: #00D4FF; --accent-green: #22C55E; --accent-purple: #A855F7;
  --accent-amber: #F59E0B; --accent-red: #EF4444; --accent-pink: #EC4899;
  --glow-cyan: 0 0 20px rgba(0,212,255,0.15);
  --radius: 12px;
  --panel-bg: rgba(30,41,59,1); --panel-hover: rgba(38,53,72,1);
  --item-bg: rgba(15,23,42,0.5); --item-hover: rgba(38,53,72,1);
  --input-bg: #1E293B; --tag-bg: rgba(0,212,255,0.08); --tag-border: rgba(0,212,255,0.15);
  height: 100vh; overflow: hidden; background: var(--bg-deep); color: var(--text-primary);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  display: flex; flex-direction: column;
}
.ops-dashboard.light {
  --bg-deep: #F8FAFC; --bg-base: #F1F5F9; --bg-card: #FFFFFF; --bg-card-hover: #F8FAFC;
  --border: #E2E8F0; --border-light: rgba(226,232,240,0.8);
  --text-primary: #0F172A; --text-secondary: #334155; --text-muted: #64748B;
  --glow-cyan: 0 0 20px rgba(0,212,255,0.08);
  --panel-bg: #FFFFFF; --panel-hover: #F8FAFC;
  --item-bg: #F8FAFC; --item-hover: #F1F5F9;
  --input-bg: #FFFFFF; --tag-bg: rgba(0,212,255,0.06); --tag-border: rgba(0,212,255,0.2);
}

.dash-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid var(--border-light); background: var(--panel-bg); backdrop-filter: blur(12px); flex-shrink: 0; }
.header-left { display: flex; align-items: center; gap: 12px; }
.logo-mark { display: flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: 10px; background: rgba(0,212,255,0.08); border: 1px solid rgba(0,212,255,0.2); }
.ops-dashboard.light .logo-mark { background: rgba(0,212,255,0.06); }
.header-left h1 { margin: 0; font-size: 18px; font-weight: 800; letter-spacing: -0.02em; background: linear-gradient(135deg, var(--text-primary) 0%, #00D4FF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.header-sub { margin: 2px 0 0; font-size: 11px; font-weight: 600; color: var(--text-muted); letter-spacing: 0.08em; text-transform: uppercase; }
.header-center { display: flex; align-items: center; gap: 16px; }
.live-badge { display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); font-size: 11px; font-weight: 700; color: var(--accent-green); letter-spacing: 0.1em; }
.pulse-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent-green); animation: pulse 2s ease-in-out infinite; }
.pulse-dot-sm { width: 5px; height: 5px; border-radius: 50%; background: var(--accent-cyan); animation: pulse 2s ease-in-out infinite; display: inline-block; }
@keyframes pulse { 0%,100% { opacity:1; box-shadow:0 0 0 0 rgba(34,197,94,0.4); } 50% { opacity:0.7; box-shadow:0 0 0 6px rgba(34,197,94,0); } }
.header-time { display: flex; flex-direction: column; align-items: center; }
.time-value { font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: 700; color: var(--accent-cyan); letter-spacing: 0.04em; }
.date-value { font-size: 11px; color: var(--text-muted); font-weight: 500; }
.header-right { display: flex; align-items: center; gap: 10px; }
.mode-switch-group { display: flex; align-items: center; gap: 2px; padding: 3px; border-radius: 8px; background: var(--item-bg); border: 1px solid var(--border-light); }
.mode-btn { display: flex; align-items: center; justify-content: center; width: 30px; height: 28px; border-radius: 6px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; transition: all 0.15s ease; }
.mode-btn:hover { color: var(--text-secondary); }
.mode-btn.active { background: var(--accent-cyan); color: #FFFFFF; }
.mode-divider { width: 1px; height: 18px; background: var(--border-light); margin: 0 2px; }

.dash-body { display: flex; flex: 1; overflow: hidden; }
.sidebar-left { width: 240px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border-light); background: var(--bg-base); overflow-y: auto; }
.sidebar-section { padding: 14px; border-bottom: 1px solid var(--border-light); }
.sidebar-section:last-child { border-bottom: none; }
.history-section { flex: 1; }
.section-header { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; }
.section-header svg { color: var(--text-muted); flex-shrink: 0; }
.section-header h2 { margin: 0; font-size: 12px; font-weight: 700; color: var(--text-muted); letter-spacing: 0.04em; text-transform: uppercase; }
.count-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; border-radius: 5px; background: rgba(0,212,255,0.12); color: var(--accent-cyan); font-size: 10px; font-weight: 700; padding: 0 5px; margin-left: auto; }
.loading-hint { padding: 10px; font-size: 12px; color: var(--text-muted); text-align: center; }
.template-list { display: flex; flex-direction: column; gap: 5px; }
.template-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid transparent; background: var(--item-bg); cursor: pointer; text-align: left; transition: all 0.2s ease; }
.template-item:hover { background: var(--item-hover); border-color: var(--border); }
.template-item.active { background: rgba(0,212,255,0.06); border-color: rgba(0,212,255,0.3); box-shadow: var(--glow-cyan); }
.template-icon { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; }
.template-icon.daily { background: rgba(0,212,255,0.1); color: var(--accent-cyan); }
.template-icon.weekly { background: rgba(168,85,247,0.1); color: var(--accent-purple); }
.template-info { flex: 1; min-width: 0; }
.template-info strong { display: block; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.template-info small { font-size: 11px; color: var(--text-muted); }
.template-status { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.04em; white-space: nowrap; }
.template-status.active { background: rgba(34,197,94,0.12); color: var(--accent-green); }
.template-status.inactive { background: rgba(148,163,184,0.12); color: var(--text-muted); }
.history-list { display: flex; flex-direction: column; gap: 5px; }
.history-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid transparent; background: var(--item-bg); cursor: pointer; text-align: left; transition: all 0.2s ease; }
.history-item:hover { background: var(--item-hover); border-color: var(--border); }
.history-item.active { background: rgba(0,212,255,0.06); border-color: rgba(0,212,255,0.3); }
.history-severity { width: 4px; height: 28px; border-radius: 2px; flex-shrink: 0; }
.history-info strong { display: block; font-size: 12px; font-weight: 600; color: var(--text-primary); }
.history-info span { font-size: 11px; color: var(--text-muted); }
.unread-dot { display: inline-block; width: 6px; height: 6px; border-radius: 999px; background: var(--accent-cyan); margin-right: 6px; vertical-align: middle; box-shadow: 0 0 8px rgba(0,212,255,0.5); }

.main-content { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.loading-center, .empty-center { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 12px; color: var(--text-muted); font-size: 14px; }

.config-view { display: flex; flex-direction: column; gap: 16px; animation: fadeIn 0.3s ease; }
.config-banner { position: relative; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border-light); }
.config-banner-bg { position: absolute; inset: 0; background: linear-gradient(135deg, rgba(0,212,255,0.08) 0%, rgba(168,85,247,0.06) 50%, rgba(34,197,94,0.04) 100%); }
.ops-dashboard.light .config-banner-bg { background: linear-gradient(135deg, rgba(0,212,255,0.04) 0%, rgba(168,85,247,0.03) 50%, rgba(34,197,94,0.02) 100%); }
.config-banner-content { position: relative; display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px; }
.config-banner-left { display: flex; align-items: center; gap: 16px; }
.config-banner-icon { display: flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 12px; flex-shrink: 0; }
.config-banner-icon.daily { background: rgba(0,212,255,0.12); color: var(--accent-cyan); }
.config-banner-icon.weekly { background: rgba(168,85,247,0.12); color: var(--accent-purple); }
.config-banner-left h2 { margin: 0; font-size: 20px; font-weight: 800; color: var(--text-primary); }
.config-banner-left p { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }
.config-actions { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.enable-row { display: flex; align-items: center; gap: 8px; }
.enable-label { font-size: 13px; font-weight: 600; color: var(--text-muted); }
.toggle-switch { width: 34px; height: 20px; border-radius: 10px; border: none; background: var(--border); padding: 2px; cursor: pointer; transition: background 0.2s ease; flex-shrink: 0; }
.toggle-switch.on { background: var(--accent-cyan); }
.toggle-knob { display: block; width: 16px; height: 16px; border-radius: 50%; background: white; transition: transform 0.2s ease; }
.toggle-switch.on .toggle-knob { transform: translateX(14px); }
.toggle-switch.lg { width: 42px; height: 24px; border-radius: 12px; padding: 2px; }
.toggle-switch.lg .toggle-knob { width: 20px; height: 20px; }
.toggle-switch.lg.on .toggle-knob { transform: translateX(18px); }
.btn-primary { display: flex; align-items: center; gap: 6px; padding: 8px 18px; border-radius: 8px; border: none; background: var(--accent-cyan); color: #FFFFFF; font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.2s ease; }
.btn-primary:hover { box-shadow: var(--glow-cyan); filter: brightness(1.1); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.config-body { display: flex; flex-direction: column; gap: 14px; }
.config-card { padding: 18px; border-radius: var(--radius); background: var(--panel-bg); border: 1px solid var(--border-light); }
.config-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.config-card-title { display: flex; align-items: center; gap: 8px; }
.config-card-title svg { color: var(--accent-cyan); }
.config-card-title h3 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.enabled-count { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 6px; background: rgba(0,212,255,0.1); color: var(--accent-cyan); }

.schedule-config { display: flex; flex-direction: column; gap: 14px; }
.schedule-row { display: flex; align-items: center; gap: 16px; }
.schedule-label { font-size: 13px; font-weight: 600; color: var(--text-muted); width: 72px; flex-shrink: 0; }
.schedule-type-row { display: flex; gap: 4px; flex: 1; }
.sch-btn { flex: 1; padding: 8px 0; border-radius: 6px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
.sch-btn:hover { border-color: var(--accent-cyan); color: var(--text-secondary); }
.sch-btn.active { background: rgba(0,212,255,0.1); border-color: rgba(0,212,255,0.4); color: var(--accent-cyan); }
.field-input { height: 36px; border-radius: 6px; border: 1px solid var(--border); background: var(--input-bg); color: var(--text-primary); padding: 0 12px; font-size: 14px; font-family: 'JetBrains Mono', monospace; outline: none; transition: border-color 0.2s ease; max-width: 140px; }
.field-input:focus { border-color: var(--accent-cyan); }
.week-day-row { display: flex; gap: 3px; }
.week-day-btn { width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; }
.week-day-btn:hover { border-color: var(--accent-cyan); color: var(--text-secondary); }
.week-day-btn.active { background: rgba(0,212,255,0.1); border-color: rgba(0,212,255,0.4); color: var(--accent-cyan); }

.module-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.module-card { padding: 14px; border-radius: 10px; background: var(--item-bg); border: 1px solid transparent; transition: all 0.25s ease; }
.module-card:hover { border-color: var(--border); }
.module-card.disabled { opacity: 0.45; }
.module-card-header { display: flex; gap: 10px; align-items: flex-start; }
.module-icon-wrap { display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0; background: rgba(148,163,184,0.08); color: var(--text-muted); transition: all 0.25s ease; }
.module-icon-wrap.on { background: rgba(0,212,255,0.1); color: var(--accent-cyan); }
.module-card-info { flex: 1; min-width: 0; }
.module-title-row { display: flex; align-items: center; gap: 6px; }
.module-card-info strong { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.module-card-info p { margin: 2px 0 0; font-size: 11px; color: var(--text-muted); }
.data-tag { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 3px; }
.data-tag.always { background: rgba(34,197,94,0.1); color: var(--accent-green); }
.data-tag.optional { background: rgba(245,158,11,0.1); color: var(--accent-amber); }
.module-range { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light); }
.range-label { font-size: 11px; font-weight: 600; color: var(--text-muted); white-space: nowrap; }
.range-btns { display: flex; gap: 3px; flex-wrap: wrap; }
.range-btn { padding: 4px 10px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.15s ease; }
.range-btn:hover { border-color: var(--accent-cyan); color: var(--text-secondary); }
.range-btn.active { background: rgba(0,212,255,0.1); border-color: rgba(0,212,255,0.4); color: var(--accent-cyan); }
.module-realtime { display: flex; align-items: center; gap: 6px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light); font-size: 11px; font-weight: 600; color: var(--accent-cyan); }

.report-meta { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.meta-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.meta-tag { font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 6px; background: var(--tag-bg); color: var(--accent-cyan); border: 1px solid var(--tag-border); }
.meta-tag.severity { border: none; }
.report-summary { margin: 0; font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-width: 640px; }
.report-time { margin: 4px 0 0; font-size: 11px; color: var(--text-muted); }
.gen-btn { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(0,212,255,0.3); background: rgba(0,212,255,0.08); color: var(--accent-cyan); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; white-space: nowrap; flex-shrink: 0; }
.gen-btn:hover { background: rgba(0,212,255,0.15); border-color: var(--accent-cyan); box-shadow: var(--glow-cyan); }
.gen-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.chart-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.chart-card { border-radius: var(--radius); background: var(--panel-bg); border: 1px solid var(--border-light); padding: 14px; transition: all 0.2s ease; }
.chart-card:hover { border-color: var(--border); }
.chart-card.span-2 { grid-column: span 2; }
.chart-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); margin-bottom: 8px; }
.chart-container { width: 100%; height: 220px; }
.chart-card.span-2 .chart-container { height: 200px; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.wallpaper-rows { display: flex; flex-direction: column; gap: 12px; }
.wallpaper-row { display: grid; grid-template-columns: 1fr 200px; gap: 12px; align-items: center; }
.wallpaper-info strong { display: block; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.wallpaper-info span { font-size: 11px; color: var(--text-muted); }
.wallpaper-bar { height: 6px; border-radius: 3px; background: rgba(148,163,184,0.1); overflow: hidden; }
.wallpaper-bar-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green)); transition: width 0.6s ease; }

.file-dist-rows { display: flex; flex-direction: column; gap: 14px; }
.file-dist-row { display: flex; flex-direction: column; gap: 6px; }
.file-dist-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.file-dist-stats { display: flex; gap: 16px; }
.stat-item { font-size: 12px; color: var(--text-muted); }
.stat-item strong { color: var(--text-primary); margin-right: 2px; font-family: 'JetBrains Mono', monospace; }
.stat-item.success strong { color: var(--accent-green); }
.stat-item.failed strong { color: var(--accent-red); }
.stat-item.exec strong { color: var(--accent-cyan); }
.stat-item.dist strong { color: var(--accent-purple); }

.text-report { padding: 22px; border-radius: var(--radius); background: var(--panel-bg); border: 1px solid var(--border-light); }

@media (max-width: 1200px) {
  .chart-grid { grid-template-columns: 1fr; }
  .chart-card.span-2 { grid-column: span 1; }
  .module-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .sidebar-left { display: none; }
  .dash-header { flex-wrap: wrap; gap: 8px; }
  .header-center { order: -1; width: 100%; justify-content: center; }
}
</style>
