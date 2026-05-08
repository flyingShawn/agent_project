<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

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
  { label: '每月', value: 'monthly' },
  { label: '自定义', value: 'interval' },
]

const reportTemplates = [
  { key: 'daily_patrol', name: '日常巡检简报', schedule: '每日 08:00', status: 'active', modules: 4 },
  { key: 'weekly_security', name: '安全合规周报', schedule: '每周一 09:00', status: 'active', modules: 4 },
  { key: 'monthly_full', name: '全量运维月报', schedule: '每月1号 10:00', status: 'draft', modules: 8 },
]

const historyReports = [
  {
    key: 'today',
    templateKey: 'daily_patrol',
    title: '日常巡检简报',
    generatedAt: '今天 08:00',
    period: '近7天',
    severity: 'normal',
    summary: '在线状态稳定，服务器磁盘占用偏高，文件分发有少量失败终端。',
  },
  {
    key: 'yesterday',
    templateKey: 'daily_patrol',
    title: '日常巡检简报',
    generatedAt: '昨天 08:00',
    period: '近7天',
    severity: 'normal',
    summary: '在线终端数量稳定，远程协助和U盘使用集中在研发、财务部门。',
  },
  {
    key: 'week',
    templateKey: 'weekly_security',
    title: '安全合规周报',
    generatedAt: '本周一 09:00',
    period: '本周',
    severity: 'attention',
    summary: '杀毒覆盖率下降至88%，壁纸屏保3台待确认，硬件资产变化7项待核验。',
  },
  {
    key: 'last_week',
    templateKey: 'weekly_security',
    title: '安全合规周报',
    generatedAt: '上周一 09:00',
    period: '上周',
    severity: 'warning',
    summary: 'U盘使用异常增长42%，未安装杀毒终端增至156台，需紧急处理。',
  },
]

const modules = ref([
  { key: 'online_status', title: '在线状态', icon: 'signal', category: 'realtime', description: '在线终端、在线率、未开机', enabled: true, range: 'realtime' },
  { key: 'server_health', title: '服务器运行', icon: 'server', category: 'realtime', description: 'CPU、内存、磁盘占用率', enabled: true, range: 'realtime' },
  { key: 'remote_top', title: '远程协助排行', icon: 'remote', category: 'period', description: '高频远程协助终端', enabled: true, range: 'last_3_days' },
  { key: 'usb_top', title: 'U盘使用排行', icon: 'usb', category: 'period', description: 'U盘设备与终端使用', enabled: true, range: 'last_7_days' },
  { key: 'wallpaper_screen', title: '壁纸屏保设置', icon: 'monitor', category: 'period', description: '策略覆盖与合规率', enabled: true, range: 'last_7_days' },
  { key: 'file_distribution', title: '文件分发统计', icon: 'folder', category: 'period', description: '推送任务量与成功率', enabled: true, range: 'last_7_days' },
  { key: 'antivirus', title: '杀毒软件安装', icon: 'shield', category: 'realtime', description: '安装覆盖率与分布', enabled: true, range: 'realtime' },
  { key: 'hardware_change', title: '硬件资产变化', icon: 'chip', category: 'period', description: '新增、变更、减少资产', enabled: true, range: 'last_7_days' },
])

const activeHistoryKey = ref('today')
const activeTemplateKey = ref('daily_patrol')
const scheduleType = ref('daily')
const scheduleTime = ref('08:00')
const showSettings = ref(false)
const currentTime = ref(new Date())

const selectedHistory = computed(() =>
  historyReports.find((r) => r.key === activeHistoryKey.value) || historyReports[0]
)

const enabledModules = computed(() => modules.value.filter((m) => m.enabled))
const enabledCount = computed(() => `${enabledModules.value.length}/${modules.value.length}`)

const severityMap = {
  normal: { label: '正常', color: '#22C55E', bg: 'rgba(34,197,94,0.12)' },
  attention: { label: '关注', color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
  warning: { label: '告警', color: '#EF4444', bg: 'rgba(239,68,68,0.12)' },
}

function toggleModule(key) {
  const m = modules.value.find((m) => m.key === key)
  if (m) m.enabled = !m.enabled
}

function updateModuleRange(key, range) {
  const m = modules.value.find((m) => m.key === key)
  if (m) m.range = range
}

const chartRefs = ref({})
const chartInstances = ref({})

const onlineTrendOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  xAxis: {
    type: 'category',
    data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '现在'],
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    min: 1200,
    max: 1600,
    splitLine: { lineStyle: { color: '#1E293B' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  series: [
    {
      type: 'line',
      data: [1342, 1289, 1426, 1451, 1438, 1412, 1426],
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#22C55E', width: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(34,197,94,0.25)' },
          { offset: 1, color: 'rgba(34,197,94,0.02)' },
        ]),
      },
    },
  ],
}))

const serverResourceOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  legend: {
    data: ['CPU', '内存', '磁盘'],
    textStyle: { color: '#94A3B8', fontSize: 11 },
    top: 4,
    right: 16,
  },
  xAxis: {
    type: 'category',
    data: ['SRV-01', 'SRV-02', 'SRV-03', 'SRV-04', 'SRV-05'],
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    max: 100,
    splitLine: { lineStyle: { color: '#1E293B' } },
    axisLabel: { color: '#94A3B8', fontSize: 11, formatter: '{value}%' },
  },
  series: [
    {
      name: 'CPU',
      type: 'bar',
      data: [42, 38, 67, 31, 55],
      itemStyle: { color: '#00D4FF', borderRadius: [3, 3, 0, 0] },
      barWidth: 12,
    },
    {
      name: '内存',
      type: 'bar',
      data: [68, 72, 81, 59, 63],
      itemStyle: { color: '#A855F7', borderRadius: [3, 3, 0, 0] },
      barWidth: 12,
    },
    {
      name: '磁盘',
      type: 'bar',
      data: [73, 56, 89, 44, 71],
      itemStyle: { color: '#F59E0B', borderRadius: [3, 3, 0, 0] },
      barWidth: 12,
    },
  ],
}))

const remoteTopOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 12, right: 40, bottom: 12, left: 120 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  xAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1E293B' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  yAxis: {
    type: 'category',
    data: ['行政部-PC027', '财务部-PC108', '研发中心-PC085'],
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#CBD5E1', fontSize: 11 },
  },
  series: [
    {
      type: 'bar',
      data: [11, 14, 18],
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#00D4FF' },
          { offset: 1, color: '#22C55E' },
        ]),
        borderRadius: [0, 4, 4, 0],
      },
      barWidth: 16,
    },
  ],
}))

const usbTopOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 12, right: 40, bottom: 12, left: 140 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  xAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1E293B' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  yAxis: {
    type: 'category',
    data: ['移动硬盘-研发备份', '闪迪高速U盘', '金士顿加密U盘'],
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#CBD5E1', fontSize: 11 },
  },
  series: [
    {
      type: 'bar',
      data: [16, 21, 32],
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#A855F7' },
          { offset: 1, color: '#EC4899' },
        ]),
        borderRadius: [0, 4, 4, 0],
      },
      barWidth: 16,
    },
  ],
}))

const antivirusPieOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'item',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  series: [
    {
      type: 'pie',
      radius: ['52%', '78%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 6, borderColor: '#0F172A', borderWidth: 2 },
      label: {
        show: true,
        position: 'outside',
        color: '#CBD5E1',
        fontSize: 11,
        formatter: '{b}\n{d}%',
      },
      labelLine: { lineStyle: { color: '#475569' } },
      data: [
        { value: 612, name: '安全客户端', itemStyle: { color: '#22C55E' } },
        { value: 489, name: '系统防护', itemStyle: { color: '#00D4FF' } },
        { value: 250, name: '第三方杀毒', itemStyle: { color: '#A855F7' } },
        { value: 156, name: '未安装', itemStyle: { color: '#EF4444' } },
      ],
    },
  ],
}))

const fileDistOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  xAxis: {
    type: 'category',
    data: ['5/2', '5/3', '5/4', '5/5', '5/6', '5/7', '5/8'],
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1E293B' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  series: [
    {
      name: '成功',
      type: 'bar',
      stack: 'total',
      data: [18, 22, 15, 20, 19, 17, 21],
      itemStyle: { color: '#22C55E', borderRadius: [0, 0, 0, 0] },
      barWidth: 18,
    },
    {
      name: '失败',
      type: 'bar',
      stack: 'total',
      data: [2, 1, 3, 1, 2, 1, 2],
      itemStyle: { color: '#EF4444', borderRadius: [3, 3, 0, 0] },
      barWidth: 18,
    },
  ],
}))

const hardwareChangeOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15,23,42,0.9)',
    borderColor: '#334155',
    textStyle: { color: '#F8FAFC', fontSize: 12 },
  },
  xAxis: {
    type: 'category',
    data: ['W12', 'W13', 'W14', 'W15', 'W16', 'W17', 'W18'],
    axisLine: { lineStyle: { color: '#334155' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#1E293B' } },
    axisLabel: { color: '#94A3B8', fontSize: 11 },
  },
  series: [
    {
      name: '新增',
      type: 'bar',
      data: [5, 3, 8, 2, 6, 4, 11],
      itemStyle: { color: '#22C55E', borderRadius: [3, 3, 0, 0] },
      barWidth: 14,
    },
    {
      name: '变更',
      type: 'bar',
      data: [12, 8, 15, 10, 9, 14, 23],
      itemStyle: { color: '#00D4FF', borderRadius: [3, 3, 0, 0] },
      barWidth: 14,
    },
    {
      name: '减少',
      type: 'bar',
      data: [2, 1, 3, 1, 2, 1, 4],
      itemStyle: { color: '#EF4444', borderRadius: [3, 3, 0, 0] },
      barWidth: 14,
    },
  ],
}))

const chartConfigs = computed(() => [
  { key: 'online_trend', option: onlineTrendOption.value, title: '在线趋势', span: 2 },
  { key: 'server_resource', option: serverResourceOption.value, title: '服务器资源', span: 2 },
  { key: 'remote_top', option: remoteTopOption.value, title: '远程协助 Top', span: 1 },
  { key: 'usb_top', option: usbTopOption.value, title: 'U盘使用 Top', span: 1 },
  { key: 'antivirus_pie', option: antivirusPieOption.value, title: '杀毒安装分布', span: 1 },
  { key: 'file_dist', option: fileDistOption.value, title: '文件分发统计', span: 1 },
  { key: 'hardware_change', option: hardwareChangeOption.value, title: '硬件资产变化', span: 2 },
])

function setChartRef(el, key) {
  if (el) chartRefs.value[key] = el
}

function initCharts() {
  Object.keys(chartRefs.value).forEach((key) => {
    if (chartInstances.value[key]) {
      chartInstances.value[key].dispose()
    }
    const el = chartRefs.value[key]
    if (!el) return
    const config = chartConfigs.value.find((c) => c.key === key)
    if (!config) return
    const instance = echarts.init(el, null, { renderer: 'canvas' })
    instance.setOption(config.option)
    chartInstances.value[key] = instance
  })
}

function handleResize() {
  Object.values(chartInstances.value).forEach((inst) => {
    if (inst) inst.resize()
  })
}

let timer = null
onMounted(() => {
  nextTick(() => {
    initCharts()
  })
  window.addEventListener('resize', handleResize)
  timer = setInterval(() => {
    currentTime.value = new Date()
  }, 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  Object.values(chartInstances.value).forEach((inst) => {
    if (inst) inst.dispose()
  })
  if (timer) clearInterval(timer)
})

watch(
  () => chartConfigs.value.map((c) => c.key),
  () => {
    nextTick(() => initCharts())
  }
)

const timeStr = computed(() => {
  const d = currentTime.value
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
})

const dateStr = computed(() => {
  const d = currentTime.value
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} 周${weekdays[d.getDay()]}`
})

const kpis = [
  { label: '在线终端', value: '1,426', unit: '台', trend: '+12', trendUp: true, color: '#22C55E' },
  { label: '在线率', value: '84.9', unit: '%', trend: '+1.2%', trendUp: true, color: '#00D4FF' },
  { label: '分发成功率', value: '96.2', unit: '%', trend: '-0.3%', trendUp: false, color: '#A855F7' },
  { label: '资产变化', value: '23', unit: '项', trend: '+7', trendUp: true, color: '#F59E0B' },
]

const attentionItems = [
  { level: 'warning', text: 'SRV-03 磁盘占用 89%，接近警戒线', module: '服务器运行', time: '2分钟前' },
  { level: 'attention', text: '3台终端屏保策略未确认', module: '壁纸屏保', time: '15分钟前' },
  { level: 'attention', text: '杀毒未安装终端 156 台', module: '杀毒安装', time: '1小时前' },
  { level: 'normal', text: '文件分发任务 126/131 完成', module: '文件分发', time: '3小时前' },
]

const wallpaperData = [
  { name: '壁纸策略', total: 1680, compliant: 1652, rate: '98.3%' },
  { name: '屏保策略', total: 1680, compliant: 1677, rate: '99.8%' },
]
</script>

<template>
  <main class="ops-dashboard">
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
        <div class="live-badge">
          <span class="pulse-dot"></span>
          <span>LIVE</span>
        </div>
        <div class="header-time">
          <span class="time-value">{{ timeStr }}</span>
          <span class="date-value">{{ dateStr }}</span>
        </div>
      </div>
      <div class="header-right">
        <div class="severity-badge" :style="{ background: severityMap[selectedHistory.severity].bg, color: severityMap[selectedHistory.severity].color }">
          {{ severityMap[selectedHistory.severity].label }}
        </div>
        <button class="settings-btn" :class="{ active: showSettings }" type="button" @click="showSettings = !showSettings">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </div>
    </header>

    <div class="dash-body">
      <aside class="sidebar-left">
        <section class="panel">
          <div class="panel-header">
            <h2>简报模板</h2>
            <span class="count-badge">{{ reportTemplates.length }}</span>
          </div>
          <div class="template-list">
            <button
              v-for="tpl in reportTemplates"
              :key="tpl.key"
              class="template-item"
              :class="{ active: activeTemplateKey === tpl.key }"
              type="button"
              @click="activeTemplateKey = tpl.key"
            >
              <div class="template-info">
                <strong>{{ tpl.name }}</strong>
                <small>{{ tpl.schedule }}</small>
              </div>
              <span class="template-status" :class="tpl.status">{{ tpl.status === 'active' ? '启用' : '草稿' }}</span>
            </button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>历史简报</h2>
            <span class="count-badge">{{ historyReports.length }}</span>
          </div>
          <div class="history-list">
            <button
              v-for="report in historyReports"
              :key="report.key"
              class="history-item"
              :class="{ active: activeHistoryKey === report.key }"
              type="button"
              @click="activeHistoryKey = report.key"
            >
              <div class="history-severity" :style="{ background: severityMap[report.severity].color }"></div>
              <div class="history-info">
                <strong>{{ report.title }}</strong>
                <span>{{ report.generatedAt }}</span>
              </div>
              <span class="history-period">{{ report.period }}</span>
            </button>
          </div>
        </section>
      </aside>

      <main class="main-content">
        <div class="report-meta">
          <div>
            <div class="meta-tags">
              <span class="meta-tag">{{ selectedHistory.period }}</span>
              <span class="meta-tag">{{ selectedHistory.title }}</span>
              <span class="meta-tag severity" :style="{ background: severityMap[selectedHistory.severity].bg, color: severityMap[selectedHistory.severity].color }">
                {{ severityMap[selectedHistory.severity].label }}
              </span>
            </div>
            <p class="report-summary">{{ selectedHistory.summary }}</p>
          </div>
          <button class="gen-btn" type="button">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            立即生成
          </button>
        </div>

        <div class="kpi-row">
          <article v-for="kpi in kpis" :key="kpi.label" class="kpi-card">
            <div class="kpi-header">
              <span class="kpi-label">{{ kpi.label }}</span>
              <span class="kpi-trend" :class="{ up: kpi.trendUp, down: !kpi.trendUp }">
                <svg v-if="kpi.trendUp" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/></svg>
                {{ kpi.trend }}
              </span>
            </div>
            <div class="kpi-value" :style="{ color: kpi.color }">
              {{ kpi.value }}<small>{{ kpi.unit }}</small>
            </div>
            <div class="kpi-bar">
              <div class="kpi-bar-fill" :style="{ width: kpi.label === '在线率' ? '84.9%' : kpi.label === '分发成功率' ? '96.2%' : '60%', background: kpi.color }"></div>
            </div>
          </article>
        </div>

        <div class="chart-grid">
          <article
            v-for="chart in chartConfigs"
            :key="chart.key"
            class="chart-card"
            :class="[`span-${chart.span}`]"
          >
            <div class="chart-title">{{ chart.title }}</div>
            <div
              :ref="(el) => setChartRef(el, chart.key)"
              class="chart-container"
            ></div>
          </article>
        </div>

        <div class="bottom-grid">
          <article class="panel wallpaper-card">
            <div class="panel-header">
              <h3>壁纸屏保合规</h3>
              <span class="meta-tag">近7天</span>
            </div>
            <div class="wallpaper-rows">
              <div v-for="item in wallpaperData" :key="item.name" class="wallpaper-row">
                <div class="wallpaper-info">
                  <strong>{{ item.name }}</strong>
                  <span>{{ item.compliant }}/{{ item.total }} 合规</span>
                </div>
                <div class="wallpaper-bar">
                  <div class="wallpaper-bar-fill" :style="{ width: item.rate }"></div>
                </div>
                <span class="wallpaper-rate">{{ item.rate }}</span>
              </div>
            </div>
          </article>

          <article class="panel attention-card">
            <div class="panel-header">
              <h3>关注项</h3>
              <span class="count-badge warn">{{ attentionItems.filter(i => i.level !== 'normal').length }}</span>
            </div>
            <div class="attention-list">
              <div v-for="item in attentionItems" :key="item.text" class="attention-row">
                <span class="attention-level" :class="item.level">
                  <svg v-if="item.level === 'warning'" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L1 21h22L12 2zm0 4l7.53 13H4.47L12 6zm-1 5v4h2v-4h-2zm0 6v2h2v-2h-2z"/></svg>
                  <svg v-else-if="item.level === 'attention'" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><line x1="12" y1="8" x2="12" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="16" r="1"/></svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                </span>
                <div class="attention-info">
                  <strong>{{ item.text }}</strong>
                  <small>{{ item.module }} · {{ item.time }}</small>
                </div>
              </div>
            </div>
          </article>
        </div>
      </main>

      <aside class="sidebar-right" :class="{ open: showSettings }">
        <div class="sidebar-right-inner">
          <div class="panel-header">
            <h2>简报设置</h2>
            <span class="count-badge">{{ enabledCount }}</span>
          </div>

          <section class="settings-section">
            <h3>生成计划</h3>
            <div class="schedule-type-row">
              <button
                v-for="st in scheduleTypes"
                :key="st.value"
                class="sch-btn"
                :class="{ active: scheduleType === st.value }"
                type="button"
                @click="scheduleType = st.value"
              >{{ st.label }}</button>
            </div>
            <label class="field-label">
              <span>生成时间</span>
              <input v-model="scheduleTime" type="time" class="field-input" />
            </label>
          </section>

          <section class="settings-section">
            <h3>展示模块</h3>
            <div class="module-list">
              <article
                v-for="m in modules"
                :key="m.key"
                class="module-item"
                :class="{ disabled: !m.enabled }"
              >
                <div class="module-top">
                  <button
                    class="toggle-switch"
                    :class="{ on: m.enabled }"
                    type="button"
                    :aria-label="`${m.enabled ? '隐藏' : '显示'}${m.title}`"
                    :aria-pressed="m.enabled"
                    @click="toggleModule(m.key)"
                  >
                    <span class="toggle-knob"></span>
                  </button>
                  <div class="module-info">
                    <strong>{{ m.title }}</strong>
                    <p>{{ m.description }}</p>
                  </div>
                </div>
                <div v-if="m.category === 'period' && m.enabled" class="module-range">
                  <button
                    v-for="range in timeRanges"
                    :key="range.value"
                    class="range-btn"
                    :class="{ active: m.range === range.value }"
                    type="button"
                    @click="updateModuleRange(m.key, range.value)"
                  >{{ range.label }}</button>
                </div>
                <div v-else-if="m.category === 'realtime' && m.enabled" class="realtime-badge">
                  <span class="pulse-dot-sm"></span>
                  实时数据
                </div>
              </article>
            </div>
          </section>
        </div>
      </aside>
    </div>

    <div v-if="showSettings" class="sidebar-overlay" @click="showSettings = false"></div>
  </main>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

.ops-dashboard {
  --bg-deep: #0A0E1A;
  --bg-base: #0F172A;
  --bg-card: #1E293B;
  --bg-card-hover: #263548;
  --border: #334155;
  --border-light: rgba(51, 65, 85, 0.5);
  --text-primary: #F8FAFC;
  --text-secondary: #CBD5E1;
  --text-muted: #94A3B8;
  --accent-cyan: #00D4FF;
  --accent-green: #22C55E;
  --accent-purple: #A855F7;
  --accent-amber: #F59E0B;
  --accent-red: #EF4444;
  --accent-pink: #EC4899;
  --glow-cyan: 0 0 20px rgba(0, 212, 255, 0.15);
  --glow-green: 0 0 20px rgba(34, 197, 94, 0.15);
  --radius: 12px;
  --radius-lg: 16px;

  height: 100vh;
  overflow: hidden;
  background: var(--bg-deep);
  color: var(--text-primary);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  display: flex;
  flex-direction: column;
}

.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-light);
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(12px);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.2);
}

.header-left h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #F8FAFC 0%, #00D4FF 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-sub {
  margin: 2px 0 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.header-center {
  display: flex;
  align-items: center;
  gap: 16px;
}

.live-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-green);
  letter-spacing: 0.1em;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: pulse 2s ease-in-out infinite;
}

.pulse-dot-sm {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent-cyan);
  animation: pulse 2s ease-in-out infinite;
  display: inline-block;
}

@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
  50% { opacity: 0.7; box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
}

.header-time {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.time-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: var(--accent-cyan);
  letter-spacing: 0.04em;
  text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
}

.date-value {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.severity-badge {
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.settings-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.settings-btn:hover,
.settings-btn.active {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.08);
}

.dash-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.sidebar-left {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  overflow-y: auto;
  border-right: 1px solid var(--border-light);
}

.panel {
  border-radius: var(--radius);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  padding: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-header h2,
.panel-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent-cyan);
  font-size: 11px;
  font-weight: 700;
  padding: 0 6px;
}

.count-badge.warn {
  background: rgba(245, 158, 11, 0.12);
  color: var(--accent-amber);
}

.template-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.template-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(15, 23, 42, 0.5);
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}

.template-item:hover {
  background: var(--bg-card-hover);
  border-color: var(--border);
}

.template-item.active {
  background: rgba(0, 212, 255, 0.06);
  border-color: rgba(0, 212, 255, 0.3);
  box-shadow: var(--glow-cyan);
}

.template-info strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.template-info small {
  font-size: 11px;
  color: var(--text-muted);
}

.template-status {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  letter-spacing: 0.04em;
}

.template-status.active {
  background: rgba(34, 197, 94, 0.12);
  color: var(--accent-green);
}

.template-status.draft {
  background: rgba(148, 163, 184, 0.12);
  color: var(--text-muted);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(15, 23, 42, 0.5);
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}

.history-item:hover {
  background: var(--bg-card-hover);
  border-color: var(--border);
}

.history-item.active {
  background: rgba(0, 212, 255, 0.06);
  border-color: rgba(0, 212, 255, 0.3);
}

.history-severity {
  width: 4px;
  height: 28px;
  border-radius: 2px;
  flex-shrink: 0;
}

.history-info strong {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.history-info span {
  font-size: 11px;
  color: var(--text-muted);
}

.history-period {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(148, 163, 184, 0.08);
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.report-meta {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.meta-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.meta-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(0, 212, 255, 0.08);
  color: var(--accent-cyan);
  border: 1px solid rgba(0, 212, 255, 0.15);
}

.meta-tag.severity {
  border: none;
}

.report-summary {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  max-width: 640px;
}

.gen-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(0, 212, 255, 0.3);
  background: rgba(0, 212, 255, 0.08);
  color: var(--accent-cyan);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  flex-shrink: 0;
}

.gen-btn:hover {
  background: rgba(0, 212, 255, 0.15);
  border-color: var(--accent-cyan);
  box-shadow: var(--glow-cyan);
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.kpi-card {
  padding: 14px;
  border-radius: var(--radius);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  transition: all 0.2s ease;
}

.kpi-card:hover {
  border-color: var(--border);
  background: var(--bg-card-hover);
}

.kpi-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.kpi-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}

.kpi-trend {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.kpi-trend.up { color: var(--accent-green); }
.kpi-trend.down { color: var(--accent-red); }

.kpi-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 10px;
}

.kpi-value small {
  font-size: 14px;
  font-weight: 600;
  margin-left: 2px;
  opacity: 0.7;
}

.kpi-bar {
  height: 3px;
  border-radius: 2px;
  background: rgba(148, 163, 184, 0.1);
  overflow: hidden;
}

.kpi-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.chart-card {
  border-radius: var(--radius);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  padding: 14px;
  transition: all 0.2s ease;
}

.chart-card:hover {
  border-color: var(--border);
}

.chart-card.span-2 {
  grid-column: span 2;
}

.chart-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 8px;
  letter-spacing: 0.02em;
}

.chart-container {
  width: 100%;
  height: 220px;
}

.chart-card.span-2 .chart-container {
  height: 200px;
}

.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.wallpaper-card,
.attention-card {
  padding: 14px;
}

.wallpaper-rows {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wallpaper-row {
  display: grid;
  grid-template-columns: 140px 1fr 52px;
  gap: 12px;
  align-items: center;
}

.wallpaper-info strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.wallpaper-info span {
  font-size: 11px;
  color: var(--text-muted);
}

.wallpaper-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(148, 163, 184, 0.1);
  overflow: hidden;
}

.wallpaper-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green));
  transition: width 0.6s ease;
}

.wallpaper-rate {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  color: var(--accent-green);
  text-align: right;
}

.attention-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.attention-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.4);
  transition: background 0.2s ease;
}

.attention-row:hover {
  background: rgba(15, 23, 42, 0.7);
}

.attention-level {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  margin-top: 1px;
}

.attention-level.warning {
  color: var(--accent-red);
  background: rgba(239, 68, 68, 0.1);
}

.attention-level.attention {
  color: var(--accent-amber);
  background: rgba(245, 158, 11, 0.1);
}

.attention-level.normal {
  color: var(--accent-green);
  background: rgba(34, 197, 94, 0.1);
}

.attention-info strong {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

.attention-info small {
  font-size: 11px;
  color: var(--text-muted);
}

.sidebar-right {
  width: 0;
  flex-shrink: 0;
  overflow: hidden;
  border-left: 1px solid transparent;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: var(--bg-base);
}

.sidebar-right.open {
  width: 300px;
  border-left-color: var(--border-light);
}

.sidebar-right-inner {
  width: 300px;
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-section {
  border-top: 1px solid var(--border-light);
  padding-top: 14px;
}

.settings-section:first-of-type {
  border-top: none;
  padding-top: 0;
}

.settings-section h3 {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.schedule-type-row {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
}

.sch-btn {
  flex: 1;
  padding: 6px 0;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sch-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--text-secondary);
}

.sch-btn.active {
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.4);
  color: var(--accent-cyan);
}

.field-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label span {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}

.field-input {
  width: 100%;
  height: 34px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0 10px;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
  outline: none;
  transition: border-color 0.2s ease;
}

.field-input:focus {
  border-color: var(--accent-cyan);
}

.module-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.module-item {
  padding: 10px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.4);
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.module-item.disabled {
  opacity: 0.4;
}

.module-top {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.toggle-switch {
  width: 34px;
  height: 20px;
  border-radius: 10px;
  border: none;
  background: var(--border);
  padding: 2px;
  cursor: pointer;
  transition: background 0.2s ease;
  flex-shrink: 0;
  margin-top: 2px;
}

.toggle-switch.on {
  background: var(--accent-cyan);
}

.toggle-knob {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
  transition: transform 0.2s ease;
}

.toggle-switch.on .toggle-knob {
  transform: translateX(14px);
}

.module-info strong {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.module-info p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}

.module-range {
  display: flex;
  gap: 3px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.range-btn {
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.range-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--text-secondary);
}

.range-btn.active {
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.4);
  color: var(--accent-cyan);
}

.realtime-badge {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--accent-cyan);
}

.sidebar-overlay {
  display: none;
}

@media (max-width: 1200px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .chart-card.span-2 {
    grid-column: span 1;
  }
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .bottom-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .sidebar-left {
    display: none;
  }
  .sidebar-right {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 50;
    width: 0;
  }
  .sidebar-right.open {
    width: 300px;
  }
  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 40;
  }
  .kpi-row {
    grid-template-columns: 1fr 1fr;
  }
  .dash-header {
    flex-wrap: wrap;
    gap: 8px;
  }
  .header-center {
    order: -1;
    width: 100%;
    justify-content: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>
