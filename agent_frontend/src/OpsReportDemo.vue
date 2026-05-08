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
]

const reportTemplates = [
  {
    key: 'daily_patrol',
    name: '日常巡检简报',
    icon: 'daily',
    schedule: '每日 08:00',
    status: 'active',
    moduleKeys: ['online_status', 'server_health', 'remote_top', 'usb_top'],
    kpis: [
      { label: '在线终端', value: '1,426', unit: '台', trend: '+12', trendUp: true, color: '#22C55E' },
      { label: '在线率', value: '84.9', unit: '%', trend: '+1.2%', trendUp: true, color: '#00D4FF' },
      { label: '远程协助', value: '43', unit: '次', trend: '-5', trendUp: false, color: '#A855F7' },
      { label: 'U盘使用', value: '69', unit: '次', trend: '+8', trendUp: true, color: '#F59E0B' },
    ],
    summary: '在线状态稳定，服务器磁盘占用偏高，远程协助集中在研发和财务部门。',
    severity: 'normal',
  },
  {
    key: 'weekly_security',
    name: '安全合规周报',
    icon: 'weekly',
    schedule: '每周一 09:00',
    status: 'active',
    moduleKeys: ['antivirus', 'wallpaper_screen', 'usb_top', 'hardware_change'],
    kpis: [
      { label: '杀毒覆盖', value: '88', unit: '%', trend: '-2%', trendUp: false, color: '#EF4444' },
      { label: '壁纸应用', value: '98.3', unit: '%', trend: '+0.1%', trendUp: true, color: '#22C55E' },
      { label: 'U盘使用', value: '69', unit: '次', trend: '+18', trendUp: true, color: '#F59E0B' },
      { label: '资产变化', value: '23', unit: '项', trend: '+7', trendUp: true, color: '#00D4FF' },
    ],
    summary: '杀毒覆盖率下降至88%，壁纸屏保3台待确认，硬件资产变化7项待核验。',
    severity: 'attention',
  },
]

const historyReports = [
  { key: 'today', templateKey: 'daily_patrol', title: '日常巡检简报', generatedAt: '今天 08:00', period: '近3天', severity: 'normal' },
  { key: 'yesterday', templateKey: 'daily_patrol', title: '日常巡检简报', generatedAt: '昨天 08:00', period: '近3天', severity: 'normal' },
  { key: 'week', templateKey: 'weekly_security', title: '安全合规周报', generatedAt: '本周一 09:00', period: '本周', severity: 'attention' },
  { key: 'last_week', templateKey: 'weekly_security', title: '安全合规周报', generatedAt: '上周一 09:00', period: '上周', severity: 'warning' },
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

const mainView = ref('report')
const activeHistoryKey = ref('today')
const activeTemplateKey = ref('daily_patrol')
const configTemplateKey = ref(null)
const scheduleType = ref('daily')
const scheduleTime = ref('08:00')
const weekDay = ref('1')
const currentTime = ref(new Date())
const viewMode = ref('visual')
const themeMode = ref('dark')
const templateEnabled = ref({ daily_patrol: true, weekly_security: true })

const templateModuleState = ref({
  daily_patrol: {
    online_status: true, server_health: true, remote_top: true, usb_top: true,
    wallpaper_screen: false, file_distribution: false, antivirus: false, hardware_change: false,
  },
  weekly_security: {
    online_status: false, server_health: false, remote_top: false, usb_top: true,
    wallpaper_screen: true, file_distribution: true, antivirus: true, hardware_change: true,
  },
})

const moduleHasData = ref({
  online_status: true,
  server_health: false,
  remote_top: true,
  usb_top: true,
  wallpaper_screen: false,
  file_distribution: false,
  antivirus: true,
  hardware_change: true,
})

const selectedHistory = computed(() =>
  historyReports.find((r) => r.key === activeHistoryKey.value) || historyReports[0]
)

const activeTemplate = computed(() =>
  reportTemplates.find((t) => t.key === activeTemplateKey.value) || reportTemplates[0]
)

const configTemplate = computed(() =>
  reportTemplates.find((t) => t.key === configTemplateKey.value) || reportTemplates[0]
)

const activeModuleKeys = computed(() => {
  if (mainView.value === 'config') {
    const state = templateModuleState.value[configTemplateKey.value]
    if (!state) return new Set()
    return new Set(Object.entries(state).filter(([, v]) => v).map(([k]) => k))
  }
  return new Set(activeTemplate.value.moduleKeys)
})

const configEnabledModules = computed(() => {
  const state = templateModuleState.value[configTemplateKey.value]
  if (!state) return []
  return allModules.filter((m) => state[m.key])
})

const configEnabledCount = computed(() => `${configEnabledModules.value.length}/${allModules.length}`)

const isConfigTemplateEnabled = computed(() => templateEnabled.value[configTemplateKey.value] ?? true)

const isDark = computed(() => themeMode.value === 'dark')

const noDataModuleCount = computed(() => {
  return allModules.filter((m) => activeModuleKeys.value.has(m.key) && !m.alwaysData && !moduleHasData.value[m.key]).length
})

const weekDays = [
  { label: '一', value: '1' },
  { label: '二', value: '2' },
  { label: '三', value: '3' },
  { label: '四', value: '4' },
  { label: '五', value: '5' },
  { label: '六', value: '6' },
  { label: '日', value: '7' },
]

const severityMap = {
  normal: { label: '正常', color: '#22C55E', bg: 'rgba(34,197,94,0.12)', lightBg: 'rgba(34,197,94,0.08)', lightColor: '#16a34a' },
  attention: { label: '关注', color: '#F59E0B', bg: 'rgba(245,158,11,0.12)', lightBg: 'rgba(245,158,11,0.08)', lightColor: '#d97706' },
  warning: { label: '告警', color: '#EF4444', bg: 'rgba(239,68,68,0.12)', lightBg: 'rgba(239,68,68,0.08)', lightColor: '#dc2626' },
}

function toggleConfigModule(key) {
  const state = templateModuleState.value[configTemplateKey.value]
  if (state) state[key] = !state[key]
}

function toggleTemplateEnabled() {
  templateEnabled.value[configTemplateKey.value] = !templateEnabled.value[configTemplateKey.value]
}

function updateModuleRange(key, range) {
  const m = allModules.find((m) => m.key === key)
  if (m) m.range = range
}

function selectTemplate(key) {
  configTemplateKey.value = key
  mainView.value = 'config'
  const tpl = reportTemplates.find((t) => t.key === key)
  if (tpl) {
    scheduleType.value = tpl.schedule.includes('每日') ? 'daily' : 'weekly'
    const timeMatch = tpl.schedule.match(/(\d{2}:\d{2})/)
    if (timeMatch) scheduleTime.value = timeMatch[1]
  }
}

function selectHistory(key) {
  activeHistoryKey.value = key
  const report = historyReports.find((r) => r.key === key)
  if (report) {
    activeTemplateKey.value = report.templateKey
  }
  mainView.value = 'report'
}

function generateNow() {}

const chartRefs = ref({})
const chartInstances = ref({})

const textColor = computed(() => isDark.value ? '#94A3B8' : '#64748B')
const axisLineColor = computed(() => isDark.value ? '#334155' : '#E2E8F0')
const splitLineColor = computed(() => isDark.value ? '#1E293B' : '#F1F5F9')
const labelColor = computed(() => isDark.value ? '#CBD5E1' : '#475569')
const tooltipBg = computed(() => isDark.value ? 'rgba(15,23,42,0.9)' : 'rgba(255,255,255,0.95)')
const tooltipBorder = computed(() => isDark.value ? '#334155' : '#E2E8F0')
const tooltipText = computed(() => isDark.value ? '#F8FAFC' : '#1E293B')

const onlineTrendOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  xAxis: { type: 'category', data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '现在'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  yAxis: { type: 'value', min: 1200, max: 1600, splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  series: [{ type: 'line', data: [1342, 1289, 1426, 1451, 1438, 1412, 1426], smooth: true, symbol: 'none', lineStyle: { color: '#22C55E', width: 2 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(34,197,94,0.25)' }, { offset: 1, color: 'rgba(34,197,94,0.02)' }]) } }],
}))

const serverResourceOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  legend: { data: ['CPU', '内存', '磁盘'], textStyle: { color: textColor.value, fontSize: 11 }, top: 4, right: 16 },
  xAxis: { type: 'category', data: ['SRV-01', 'SRV-02', 'SRV-03', 'SRV-04', 'SRV-05'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  yAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11, formatter: '{value}%' } },
  series: [
    { name: 'CPU', type: 'bar', data: [42, 38, 67, 31, 55], itemStyle: { color: '#00D4FF', borderRadius: [3, 3, 0, 0] }, barWidth: 12 },
    { name: '内存', type: 'bar', data: [68, 72, 81, 59, 63], itemStyle: { color: '#A855F7', borderRadius: [3, 3, 0, 0] }, barWidth: 12 },
    { name: '磁盘', type: 'bar', data: [73, 56, 89, 44, 71], itemStyle: { color: '#F59E0B', borderRadius: [3, 3, 0, 0] }, barWidth: 12 },
  ],
}))

const remoteTopOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 12, right: 40, bottom: 12, left: 120 },
  tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  yAxis: { type: 'category', data: ['行政部-PC027', '财务部-PC108', '研发中心-PC085'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: labelColor.value, fontSize: 11 } },
  series: [{ type: 'bar', data: [11, 14, 18], itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#00D4FF' }, { offset: 1, color: '#22C55E' }]), borderRadius: [0, 4, 4, 0] }, barWidth: 16 }],
}))

const usbDeviceTopOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 12, right: 40, bottom: 12, left: 140 },
  tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  yAxis: { type: 'category', data: ['移动硬盘-研发备份', '闪迪高速U盘', '金士顿加密U盘'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: labelColor.value, fontSize: 11 } },
  series: [{ type: 'bar', data: [16, 21, 32], itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#A855F7' }, { offset: 1, color: '#EC4899' }]), borderRadius: [0, 4, 4, 0] }, barWidth: 16 }],
}))

const usbComputerTopOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 12, right: 40, bottom: 12, left: 120 },
  tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  yAxis: { type: 'category', data: ['研发中心-PC085', '财务部-PC108', '行政部-PC027'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: labelColor.value, fontSize: 11 } },
  series: [{ type: 'bar', data: [28, 19, 14], itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#00D4FF' }, { offset: 1, color: '#A855F7' }]), borderRadius: [0, 4, 4, 0] }, barWidth: 16 }],
}))

const antivirusPieOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'item', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  series: [{
    type: 'pie', radius: ['52%', '78%'], center: ['50%', '50%'], avoidLabelOverlap: false,
    itemStyle: { borderRadius: 6, borderColor: isDark.value ? '#0F172A' : '#FFFFFF', borderWidth: 2 },
    label: { show: true, position: 'outside', color: labelColor.value, fontSize: 11, formatter: '{b}\n{d}%' },
    labelLine: { lineStyle: { color: isDark.value ? '#475569' : '#CBD5E1' } },
    data: [
      { value: 57, name: '火绒安全', itemStyle: { color: '#22C55E' } },
      { value: 20, name: '360安全卫士', itemStyle: { color: '#00D4FF' } },
      { value: 11, name: '天擎', itemStyle: { color: '#A855F7' } },
      { value: 12, name: '未安装', itemStyle: { color: '#EF4444' } },
    ],
  }],
}))

const hardwareChangeOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { top: 30, right: 16, bottom: 24, left: 44 },
  tooltip: { trigger: 'axis', backgroundColor: tooltipBg.value, borderColor: tooltipBorder.value, textStyle: { color: tooltipText.value, fontSize: 12 } },
  xAxis: { type: 'category', data: ['W12', 'W13', 'W14', 'W15', 'W16', 'W17', 'W18'], axisLine: { lineStyle: { color: axisLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: splitLineColor.value } }, axisLabel: { color: textColor.value, fontSize: 11 } },
  series: [
    { name: '新增', type: 'bar', data: [5, 3, 8, 2, 6, 4, 11], itemStyle: { color: '#22C55E', borderRadius: [3, 3, 0, 0] }, barWidth: 14 },
    { name: '变更', type: 'bar', data: [12, 8, 15, 10, 9, 14, 23], itemStyle: { color: '#00D4FF', borderRadius: [3, 3, 0, 0] }, barWidth: 14 },
    { name: '减少', type: 'bar', data: [2, 1, 3, 1, 2, 1, 4], itemStyle: { color: '#EF4444', borderRadius: [3, 3, 0, 0] }, barWidth: 14 },
  ],
}))

const chartConfigs = computed(() => {
  const configs = []
  if (activeModuleKeys.value.has('online_status')) {
    configs.push({ key: 'online_trend', option: onlineTrendOption.value, title: '在线趋势', span: 2, moduleKey: 'online_status' })
  }
  if (activeModuleKeys.value.has('server_health')) {
    configs.push({ key: 'server_resource', option: serverResourceOption.value, title: '服务器资源', span: 2, moduleKey: 'server_health' })
  }
  if (activeModuleKeys.value.has('remote_top')) {
    configs.push({ key: 'remote_top', option: remoteTopOption.value, title: '远程协助 Top', span: 1, moduleKey: 'remote_top' })
  }
  if (activeModuleKeys.value.has('usb_top')) {
    configs.push({ key: 'usb_device_top', option: usbDeviceTopOption.value, title: 'U盘设备 Top', span: 1, moduleKey: 'usb_top' })
    configs.push({ key: 'usb_computer_top', option: usbComputerTopOption.value, title: 'U盘电脑 Top', span: 1, moduleKey: 'usb_top' })
  }
  if (activeModuleKeys.value.has('antivirus')) {
    configs.push({ key: 'antivirus_pie', option: antivirusPieOption.value, title: '杀毒软件分布', span: 1, moduleKey: 'antivirus' })
  }
  if (activeModuleKeys.value.has('hardware_change')) {
    configs.push({ key: 'hardware_change', option: hardwareChangeOption.value, title: '硬件资产变化', span: 2, moduleKey: 'hardware_change' })
  }
  return configs
})

const wallpaperData = [
  { name: '壁纸策略', applied: 1652, total: 1680, pending: 18, failed: 10, rate: '98.3%' },
  { name: '屏保策略', applied: 1677, total: 1680, pending: 2, failed: 1, rate: '99.8%' },
]

const fileDistTasks = [
  { name: '安全补丁分发-5月', distributed: 275, success: 230, failed: 45, execSuccess: 200 },
  { name: '办公软件更新', distributed: 180, success: 168, failed: 12, execSuccess: 155 },
  { name: '驱动程序升级', distributed: 120, success: 112, failed: 8, execSuccess: 105 },
]

const attentionItems = [
  { level: 'warning', text: 'SRV-03 磁盘占用 89%，接近警戒线', module: '服务器运行', time: '2分钟前' },
  { level: 'attention', text: '3台终端屏保策略未应用', module: '壁纸屏保', time: '15分钟前' },
  { level: 'attention', text: '杀毒未安装终端占比 12%', module: '杀毒安装', time: '1小时前' },
  { level: 'normal', text: '文件分发任务 230/275 成功', module: '文件分发', time: '3小时前' },
]

const textSections = computed(() => {
  const sections = []
  if (activeModuleKeys.value.has('online_status')) {
    sections.push({ title: '在线状态', hasData: true, lines: ['当前在线终端 1,426 台，在线率 84.9%，整体稳定。', '未开机设备 253 台，较昨日减少 12 台。'] })
  }
  if (activeModuleKeys.value.has('server_health')) {
    sections.push({ title: '服务器运行', hasData: moduleHasData.value.server_health, lines: moduleHasData.value.server_health ? ['SRV-03 磁盘占用 89% 需关注，其余服务器资源正常。', '5台服务器平均 CPU 46.6%，内存 68.6%，磁盘 66.6%。'] : [] })
  }
  if (activeModuleKeys.value.has('remote_top')) {
    sections.push({ title: '远程协助排行', hasData: moduleHasData.value.remote_top, lines: moduleHasData.value.remote_top ? ['近3天远程协助共 43 次，研发中心-PC085 以 18 次居首。', '远程协助集中在研发和财务部门。'] : [] })
  }
  if (activeModuleKeys.value.has('usb_top')) {
    sections.push({ title: 'U盘使用排行', hasData: moduleHasData.value.usb_top, lines: moduleHasData.value.usb_top ? ['近7天 U盘使用 69 次，金士顿加密U盘使用最多（32次）。', '使用U盘最多的电脑为研发中心-PC085（28次）。'] : [] })
  }
  if (activeModuleKeys.value.has('wallpaper_screen')) {
    sections.push({ title: '壁纸屏保策略应用', hasData: moduleHasData.value.wallpaper_screen, lines: moduleHasData.value.wallpaper_screen ? ['壁纸策略已应用 1,652/1,680 台，待应用 18 台，失败 10 台。', '屏保策略已应用 1,677/1,680 台，待应用 2 台，失败 1 台。'] : [] })
  }
  if (activeModuleKeys.value.has('file_distribution')) {
    sections.push({ title: '文件分发统计', hasData: moduleHasData.value.file_distribution, lines: moduleHasData.value.file_distribution ? ['安全补丁分发-5月：分发 275 台，成功 230 台，失败 45 台，执行成功 200 台。', '办公软件更新：分发 180 台，成功 168 台，失败 12 台。'] : [] })
  }
  if (activeModuleKeys.value.has('antivirus')) {
    sections.push({ title: '杀毒软件安装', hasData: true, lines: ['已安装杀毒软件终端 1,507 台，覆盖率 88%。', '火绒安全占比 57%，360安全卫士占比 20%，未安装 12%。'] })
  }
  if (activeModuleKeys.value.has('hardware_change')) {
    sections.push({ title: '硬件资产变化', hasData: true, lines: ['近7天硬件资产新增 11 项，变更 23 项，减少 4 项。', '其中 7 项变更建议人工确认。'] })
  }
  return sections
})

const moduleIconMap = {
  online: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  server: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
  remote: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/><path d="M6 10h4"/><path d="M14 10h4"/></svg>`,
  usb: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="m4.93 10.93 1.41 1.41"/><path d="M2 18h2"/><path d="M20 18h2"/><path d="m19.07 10.93-1.41 1.41"/><path d="M22 22H2"/><path d="m16 6-4-4-4 4"/><path d="m16 18-4 4-4-4"/></svg>`,
  wallpaper: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
  file: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>`,
  antivirus: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>`,
  hardware: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`,
}

function getModuleIcon(iconKey) {
  return moduleIconMap[iconKey] || ''
}

function setChartRef(el, key) {
  if (el) chartRefs.value[key] = el
}

function initCharts() {
  if (mainView.value !== 'report') return
  Object.keys(chartInstances.value).forEach((key) => {
    if (!chartConfigs.value.find((c) => c.key === key)) {
      chartInstances.value[key].dispose()
      delete chartInstances.value[key]
    }
  })
  chartConfigs.value.forEach((config) => {
    if (!moduleHasData.value[config.moduleKey]) return
    if (chartInstances.value[config.key]) {
      chartInstances.value[config.key].dispose()
    }
    const el = chartRefs.value[config.key]
    if (!el) return
    const instance = echarts.init(el, null, { renderer: 'canvas' })
    instance.setOption(config.option)
    chartInstances.value[config.key] = instance
  })
}

function handleResize() {
  Object.values(chartInstances.value).forEach((inst) => { if (inst) inst.resize() })
}

let timer = null
onMounted(() => {
  nextTick(() => initCharts())
  window.addEventListener('resize', handleResize)
  timer = setInterval(() => { currentTime.value = new Date() }, 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  Object.values(chartInstances.value).forEach((inst) => { if (inst) inst.dispose() })
  if (timer) clearInterval(timer)
})

watch([activeTemplateKey, viewMode, themeMode, moduleHasData, mainView], () => {
  chartRefs.value = {}
  chartInstances.value = {}
  nextTick(() => initCharts())
}, { deep: true })

const timeStr = computed(() => {
  const d = currentTime.value
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
})

const dateStr = computed(() => {
  const d = currentTime.value
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} 周${weekdays[d.getDay()]}`
})
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
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            <h2>简报模板</h2>
          </div>
          <div class="template-list">
            <button
              v-for="tpl in reportTemplates"
              :key="tpl.key"
              class="template-item"
              :class="{ active: mainView === 'config' && configTemplateKey === tpl.key }"
              type="button"
              @click="selectTemplate(tpl.key)"
            >
              <div class="template-icon" :class="tpl.icon">
                <svg v-if="tpl.icon === 'daily'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              </div>
              <div class="template-info">
                <strong>{{ tpl.name }}</strong>
                <small>{{ tpl.schedule }}</small>
              </div>
              <span class="template-status" :class="templateEnabled[tpl.key] ? 'active' : 'inactive'">{{ templateEnabled[tpl.key] ? '启用' : '停用' }}</span>
            </button>
          </div>
        </section>

        <section class="sidebar-section history-section">
          <div class="section-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <h2>历史简报</h2>
            <span class="count-badge">{{ historyReports.length }}</span>
          </div>
          <div class="history-list">
            <button
              v-for="report in historyReports"
              :key="report.key"
              class="history-item"
              :class="{ active: mainView === 'report' && activeHistoryKey === report.key }"
              type="button"
              @click="selectHistory(report.key)"
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
        <!-- 配置视图：点击模板时显示 -->
        <div v-if="mainView === 'config'" class="config-view">
          <div class="config-banner">
            <div class="config-banner-bg"></div>
            <div class="config-banner-content">
              <div class="config-banner-left">
                <div class="config-banner-icon" :class="configTemplate.icon">
                  <svg v-if="configTemplate.icon === 'daily'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                </div>
                <div>
                  <h2>{{ configTemplate.name }}</h2>
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
                <button class="btn-primary" type="button" @click="generateNow">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  立即生成
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
                    <button v-for="st in scheduleTypes" :key="st.value" class="sch-btn" :class="{ active: scheduleType === st.value }" type="button" @click="scheduleType = st.value">{{ st.label }}</button>
                  </div>
                </div>
                <div class="schedule-row">
                  <span class="schedule-label">生成时间</span>
                  <input v-model="scheduleTime" type="time" class="field-input" />
                </div>
                <div v-if="scheduleType === 'weekly'" class="schedule-row">
                  <span class="schedule-label">生成日</span>
                  <div class="week-day-row">
                    <button v-for="wd in weekDays" :key="wd.value" class="week-day-btn" :class="{ active: weekDay === wd.value }" type="button" @click="weekDay = wd.value">{{ wd.label }}</button>
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
                <article v-for="m in allModules" :key="m.key" class="module-card" :class="{ disabled: !templateModuleState[configTemplateKey]?.[m.key], [m.category]: true }">
                  <div class="module-card-header">
                    <div class="module-icon-wrap" :class="{ on: templateModuleState[configTemplateKey]?.[m.key] }" v-html="getModuleIcon(m.icon)"></div>
                    <div class="module-card-info">
                      <div class="module-title-row">
                        <strong>{{ m.title }}</strong>
                        <span v-if="m.alwaysData" class="data-tag always">必选</span>
                        <span v-else class="data-tag optional">可选</span>
                      </div>
                      <p>{{ m.description }}</p>
                    </div>
                    <button class="toggle-switch" :class="{ on: templateModuleState[configTemplateKey]?.[m.key] }" type="button" @click="toggleConfigModule(m.key)">
                      <span class="toggle-knob"></span>
                    </button>
                  </div>
                  <div v-if="m.category === 'period' && templateModuleState[configTemplateKey]?.[m.key]" class="module-range">
                    <span class="range-label">统计周期</span>
                    <div class="range-btns">
                      <button v-for="range in timeRanges" :key="range.value" class="range-btn" :class="{ active: m.range === range.value }" type="button" @click="updateModuleRange(m.key, range.value)">{{ range.label }}</button>
                    </div>
                  </div>
                  <div v-else-if="m.category === 'realtime' && templateModuleState[configTemplateKey]?.[m.key]" class="module-realtime">
                    <span class="pulse-dot-sm"></span>
                    <span>实时数据，无需配置周期</span>
                  </div>
                </article>
              </div>
              <div class="data-note">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                <span>标记"可选"的模块可能无数据，无数据时将显示为空状态占位</span>
              </div>
            </section>
          </div>
        </div>

        <!-- 简报视图：点击历史简报时显示 -->
        <template v-if="mainView === 'report'">
          <div class="report-meta">
            <div>
              <div class="meta-tags">
                <span class="meta-tag">{{ selectedHistory.period }}</span>
                <span class="meta-tag">{{ activeTemplate.name }}</span>
                <span class="meta-tag severity" :style="{ background: isDark ? severityMap[selectedHistory.severity].bg : severityMap[selectedHistory.severity].lightBg, color: isDark ? severityMap[selectedHistory.severity].color : severityMap[selectedHistory.severity].lightColor }">
                  {{ severityMap[selectedHistory.severity].label }}
                </span>
              </div>
              <p class="report-summary">{{ activeTemplate.summary }}</p>
            </div>
            <button class="gen-btn" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              立即生成
            </button>
          </div>

          <div v-if="viewMode === 'visual'" class="kpi-row">
            <article v-for="kpi in activeTemplate.kpis" :key="kpi.label" class="kpi-card">
              <div class="kpi-header">
                <span class="kpi-label">{{ kpi.label }}</span>
                <span class="kpi-trend" :class="{ up: kpi.trendUp, down: !kpi.trendUp }">
                  <svg v-if="kpi.trendUp" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/></svg>
                  <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/></svg>
                  {{ kpi.trend }}
                </span>
              </div>
              <div class="kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}<small>{{ kpi.unit }}</small></div>
              <div class="kpi-bar"><div class="kpi-bar-fill" :style="{ width: '70%', background: kpi.color }"></div></div>
            </article>
          </div>

          <div v-if="viewMode === 'visual' && noDataModuleCount > 0" class="no-data-hint">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            <span>{{ noDataModuleCount }} 个模块暂无数据，显示为空状态占位</span>
          </div>

          <div v-if="viewMode === 'visual'" class="chart-grid">
            <article v-for="chart in chartConfigs" :key="chart.key" class="chart-card" :class="[`span-${chart.span}`]">
              <div class="chart-title">{{ chart.title }}</div>
              <div v-if="moduleHasData[chart.moduleKey]" :ref="(el) => setChartRef(el, chart.key)" class="chart-container"></div>
              <div v-else class="chart-empty">
                <div class="empty-icon">
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.3"/>
                    <line x1="14" y1="20" x2="22" y2="20" stroke="currentColor" stroke-width="1.5" opacity="0.2"/>
                    <line x1="14" y1="26" x2="28" y2="26" stroke="currentColor" stroke-width="1.5" opacity="0.2"/>
                    <line x1="14" y1="32" x2="20" y2="32" stroke="currentColor" stroke-width="1.5" opacity="0.2"/>
                    <line x1="28" y1="4" x2="40" y2="40" stroke="currentColor" stroke-width="1.5" opacity="0.25"/>
                    <line x1="40" y1="4" x2="28" y2="40" stroke="currentColor" stroke-width="1.5" opacity="0.25"/>
                  </svg>
                </div>
                <p class="empty-title">暂无数据</p>
                <p class="empty-desc">{{ allModules.find(m => m.key === chart.moduleKey)?.description || '' }}</p>
              </div>
            </article>

            <article v-if="activeModuleKeys.has('wallpaper_screen')" class="chart-card span-2">
              <div class="chart-title">壁纸屏保策略应用情况</div>
              <div v-if="moduleHasData.wallpaper_screen" class="wallpaper-rows">
                <div v-for="item in wallpaperData" :key="item.name" class="wallpaper-row">
                  <div class="wallpaper-info">
                    <strong>{{ item.name }}</strong>
                    <span>已应用 {{ item.applied }}/{{ item.total }} · 待应用 {{ item.pending }} · 失败 {{ item.failed }}</span>
                  </div>
                  <div class="wallpaper-bar"><div class="wallpaper-bar-fill" :style="{ width: item.rate }"></div></div>
                  <span class="wallpaper-rate">{{ item.rate }}</span>
                </div>
              </div>
              <div v-else class="chart-empty">
                <div class="empty-icon"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.3"/><line x1="28" y1="4" x2="40" y2="40" stroke="currentColor" stroke-width="1.5" opacity="0.25"/><line x1="40" y1="4" x2="28" y2="40" stroke="currentColor" stroke-width="1.5" opacity="0.25"/></svg></div>
                <p class="empty-title">暂无数据</p>
                <p class="empty-desc">壁纸屏保策略应用情况</p>
              </div>
            </article>

            <article v-if="activeModuleKeys.has('file_distribution')" class="chart-card span-2">
              <div class="chart-title">文件分发任务</div>
              <div v-if="moduleHasData.file_distribution" class="file-dist-rows">
                <div v-for="task in fileDistTasks" :key="task.name" class="file-dist-row">
                  <div class="file-dist-name">{{ task.name }}</div>
                  <div class="file-dist-stats">
                    <span class="stat-item dist"><strong>{{ task.distributed }}</strong>分发</span>
                    <span class="stat-item success"><strong>{{ task.success }}</strong>成功</span>
                    <span class="stat-item failed"><strong>{{ task.failed }}</strong>失败</span>
                    <span class="stat-item exec"><strong>{{ task.execSuccess }}</strong>执行成功</span>
                  </div>
                  <div class="file-dist-bar">
                    <div class="file-dist-bar-success" :style="{ width: (task.success / task.distributed * 100) + '%' }"></div>
                    <div class="file-dist-bar-failed" :style="{ width: (task.failed / task.distributed * 100) + '%', left: (task.success / task.distributed * 100) + '%' }"></div>
                  </div>
                </div>
              </div>
              <div v-else class="chart-empty">
                <div class="empty-icon"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.3"/><line x1="28" y1="4" x2="40" y2="40" stroke="currentColor" stroke-width="1.5" opacity="0.25"/><line x1="40" y1="4" x2="28" y2="40" stroke="currentColor" stroke-width="1.5" opacity="0.25"/></svg></div>
                <p class="empty-title">暂无数据</p>
                <p class="empty-desc">文件分发任务执行情况</p>
              </div>
            </article>

            <article class="chart-card span-2">
              <div class="panel-header"><h3>关注项</h3><span class="count-badge warn">{{ attentionItems.filter(i => i.level !== 'normal').length }}</span></div>
              <div class="attention-list">
                <div v-for="item in attentionItems" :key="item.text" class="attention-row">
                  <span class="attention-level" :class="item.level">
                    <svg v-if="item.level === 'warning'" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L1 21h22L12 2zm0 4l7.53 13H4.47L12 6zm-1 5v4h2v-4h-2zm0 6v2h2v-2h-2z"/></svg>
                    <svg v-else-if="item.level === 'attention'" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><line x1="12" y1="8" x2="12" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="16" r="1"/></svg>
                    <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                  </span>
                  <div class="attention-info"><strong>{{ item.text }}</strong><small>{{ item.module }} · {{ item.time }}</small></div>
                </div>
              </div>
            </article>
          </div>

          <article v-if="viewMode === 'text'" class="text-report panel">
            <div class="text-report-header">
              <div>
                <p class="section-label">{{ activeTemplate.name }}</p>
                <h2>{{ selectedHistory.generatedAt }} 生成</h2>
              </div>
              <span class="meta-tag">{{ selectedHistory.period }}</span>
            </div>
            <p class="lead-text">{{ activeTemplate.summary }}</p>
            <section v-for="section in textSections" :key="section.title" class="report-section">
              <h4>{{ section.title }}</h4>
              <ul v-if="section.hasData">
                <li v-for="line in section.lines" :key="line">{{ line }}</li>
              </ul>
              <div v-else class="text-empty">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <span>暂无数据</span>
              </div>
            </section>
          </article>
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

.dash-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-bottom: 1px solid var(--border-light);
  background: var(--panel-bg); backdrop-filter: blur(12px); flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.logo-mark {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; border-radius: 10px;
  background: rgba(0,212,255,0.08); border: 1px solid rgba(0,212,255,0.2);
}
.ops-dashboard.light .logo-mark { background: rgba(0,212,255,0.06); }
.header-left h1 {
  margin: 0; font-size: 18px; font-weight: 800; letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--text-primary) 0%, #00D4FF 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.header-sub { margin: 2px 0 0; font-size: 11px; font-weight: 600; color: var(--text-muted); letter-spacing: 0.08em; text-transform: uppercase; }
.header-center { display: flex; align-items: center; gap: 16px; }
.live-badge {
  display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px;
  background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3);
  font-size: 11px; font-weight: 700; color: var(--accent-green); letter-spacing: 0.1em;
}
.pulse-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent-green); animation: pulse 2s ease-in-out infinite; }
.pulse-dot-sm { width: 5px; height: 5px; border-radius: 50%; background: var(--accent-cyan); animation: pulse 2s ease-in-out infinite; display: inline-block; }
@keyframes pulse { 0%,100% { opacity:1; box-shadow:0 0 0 0 rgba(34,197,94,0.4); } 50% { opacity:0.7; box-shadow:0 0 0 6px rgba(34,197,94,0); } }
.header-time { display: flex; flex-direction: column; align-items: center; }
.time-value { font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: 700; color: var(--accent-cyan); letter-spacing: 0.04em; }
.ops-dashboard.light .time-value { text-shadow: none; }
.date-value { font-size: 11px; color: var(--text-muted); font-weight: 500; }
.header-right { display: flex; align-items: center; gap: 10px; }
.mode-switch-group { display: flex; align-items: center; gap: 2px; padding: 3px; border-radius: 8px; background: var(--item-bg); border: 1px solid var(--border-light); }
.mode-btn {
  display: flex; align-items: center; justify-content: center; width: 30px; height: 28px;
  border-radius: 6px; border: none; background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all 0.15s ease;
}
.mode-btn:hover { color: var(--text-secondary); }
.mode-btn.active { background: var(--accent-cyan); color: #FFFFFF; }
.mode-divider { width: 1px; height: 18px; background: var(--border-light); margin: 0 2px; }

.dash-body { display: flex; flex: 1; overflow: hidden; }
.sidebar-left {
  width: 240px; flex-shrink: 0; display: flex; flex-direction: column;
  border-right: 1px solid var(--border-light); background: var(--bg-base);
  overflow-y: auto;
}
.sidebar-section { padding: 14px; border-bottom: 1px solid var(--border-light); }
.sidebar-section:last-child { border-bottom: none; }
.history-section { flex: 1; }
.section-header {
  display: flex; align-items: center; gap: 6px; margin-bottom: 10px;
}
.section-header svg { color: var(--text-muted); flex-shrink: 0; }
.section-header h2 { margin: 0; font-size: 12px; font-weight: 700; color: var(--text-muted); letter-spacing: 0.04em; text-transform: uppercase; }
.count-badge {
  display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px;
  border-radius: 5px; background: rgba(0,212,255,0.12); color: var(--accent-cyan); font-size: 10px; font-weight: 700; padding: 0 5px; margin-left: auto;
}
.count-badge.warn { background: rgba(245,158,11,0.12); color: var(--accent-amber); }
.template-list { display: flex; flex-direction: column; gap: 5px; }
.template-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 10px 12px; border-radius: 8px; border: 1px solid transparent;
  background: var(--item-bg); cursor: pointer; text-align: left; transition: all 0.2s ease;
}
.template-item:hover { background: var(--item-hover); border-color: var(--border); }
.template-item.active { background: rgba(0,212,255,0.06); border-color: rgba(0,212,255,0.3); box-shadow: var(--glow-cyan); }
.ops-dashboard.light .template-item.active { background: rgba(0,212,255,0.04); }
.template-icon {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
}
.template-icon.daily { background: rgba(0,212,255,0.1); color: var(--accent-cyan); }
.template-icon.weekly { background: rgba(168,85,247,0.1); color: var(--accent-purple); }
.template-info { flex: 1; min-width: 0; }
.template-info strong { display: block; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.template-info small { font-size: 11px; color: var(--text-muted); }
.template-status { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.04em; white-space: nowrap; }
.template-status.lg { font-size: 11px; padding: 4px 10px; }
.template-status.active { background: rgba(34,197,94,0.12); color: var(--accent-green); }
.template-status.inactive { background: rgba(148,163,184,0.12); color: var(--text-muted); }
.template-status.draft { background: rgba(148,163,184,0.12); color: var(--text-muted); }
.history-list { display: flex; flex-direction: column; gap: 5px; }
.history-item {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px;
  border-radius: 8px; border: 1px solid transparent; background: var(--item-bg);
  cursor: pointer; text-align: left; transition: all 0.2s ease;
}
.history-item:hover { background: var(--item-hover); border-color: var(--border); }
.history-item.active { background: rgba(0,212,255,0.06); border-color: rgba(0,212,255,0.3); }
.history-severity { width: 4px; height: 28px; border-radius: 2px; flex-shrink: 0; }
.history-info strong { display: block; font-size: 12px; font-weight: 600; color: var(--text-primary); }
.history-info span { font-size: 11px; color: var(--text-muted); }
.history-period { margin-left: auto; font-size: 10px; font-weight: 600; color: var(--text-muted); padding: 2px 6px; border-radius: 4px; background: rgba(148,163,184,0.08); white-space: nowrap; }

.main-content { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }

.config-view { display: flex; flex-direction: column; gap: 16px; animation: fadeIn 0.3s ease; }

.config-banner {
  position: relative; border-radius: var(--radius); overflow: hidden;
  border: 1px solid var(--border-light);
}
.config-banner-bg {
  position: absolute; inset: 0;
  background: linear-gradient(135deg, rgba(0,212,255,0.08) 0%, rgba(168,85,247,0.06) 50%, rgba(34,197,94,0.04) 100%);
}
.ops-dashboard.light .config-banner-bg {
  background: linear-gradient(135deg, rgba(0,212,255,0.04) 0%, rgba(168,85,247,0.03) 50%, rgba(34,197,94,0.02) 100%);
}
.config-banner-content {
  position: relative; display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  padding: 20px;
}
.config-banner-left { display: flex; align-items: center; gap: 16px; }
.config-banner-icon {
  display: flex; align-items: center; justify-content: center;
  width: 48px; height: 48px; border-radius: 12px; flex-shrink: 0;
}
.config-banner-icon.daily { background: rgba(0,212,255,0.12); color: var(--accent-cyan); }
.config-banner-icon.weekly { background: rgba(168,85,247,0.12); color: var(--accent-purple); }
.config-banner-left h2 { margin: 0; font-size: 20px; font-weight: 800; color: var(--text-primary); }
.config-banner-left p { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }
.config-actions { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.enable-row { display: flex; align-items: center; gap: 8px; }
.enable-label { font-size: 13px; font-weight: 600; color: var(--text-muted); }
.toggle-switch.lg { width: 42px; height: 24px; border-radius: 12px; padding: 2px; }
.toggle-switch.lg .toggle-knob { width: 20px; height: 20px; }
.toggle-switch.lg.on .toggle-knob { transform: translateX(18px); }
.btn-primary {
  display: flex; align-items: center; gap: 6px; padding: 8px 18px; border-radius: 8px;
  border: none; background: var(--accent-cyan); color: #FFFFFF; font-size: 13px; font-weight: 700;
  cursor: pointer; transition: all 0.2s ease;
}
.btn-primary:hover { box-shadow: var(--glow-cyan); filter: brightness(1.1); }

.config-body { display: flex; flex-direction: column; gap: 14px; }
.config-card {
  padding: 18px; border-radius: var(--radius); background: var(--panel-bg); border: 1px solid var(--border-light);
}
.config-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.config-card-title { display: flex; align-items: center; gap: 8px; }
.config-card-title svg { color: var(--accent-cyan); }
.config-card-title h3 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.enabled-count {
  font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 6px;
  background: rgba(0,212,255,0.1); color: var(--accent-cyan);
}

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
.week-day-btn {
  width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border);
  background: transparent; color: var(--text-muted); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center;
}
.week-day-btn:hover { border-color: var(--accent-cyan); color: var(--text-secondary); }
.week-day-btn.active { background: rgba(0,212,255,0.1); border-color: rgba(0,212,255,0.4); color: var(--accent-cyan); }

.module-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.module-card { padding: 14px; border-radius: 10px; background: var(--item-bg); border: 1px solid transparent; transition: all 0.25s ease; position: relative; }
.module-card:hover { border-color: var(--border); }
.module-card.disabled { opacity: 0.45; }
.module-card-header { display: flex; gap: 10px; align-items: flex-start; }
.module-icon-wrap {
  display: flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0;
  background: rgba(148,163,184,0.08); color: var(--text-muted); transition: all 0.25s ease;
}
.module-icon-wrap.on { background: rgba(0,212,255,0.1); color: var(--accent-cyan); }
.module-card-info { flex: 1; min-width: 0; }
.module-title-row { display: flex; align-items: center; gap: 6px; }
.module-card-info strong { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.module-card-info p { margin: 2px 0 0; font-size: 11px; color: var(--text-muted); }
.data-tag { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 3px; letter-spacing: 0.02em; }
.data-tag.always { background: rgba(34,197,94,0.1); color: var(--accent-green); }
.data-tag.optional { background: rgba(245,158,11,0.1); color: var(--accent-amber); }
.toggle-switch { width: 34px; height: 20px; border-radius: 10px; border: none; background: var(--border); padding: 2px; cursor: pointer; transition: background 0.2s ease; flex-shrink: 0; margin-top: 2px; }
.toggle-switch.on { background: var(--accent-cyan); }
.toggle-knob { display: block; width: 16px; height: 16px; border-radius: 50%; background: white; transition: transform 0.2s ease; }
.toggle-switch.on .toggle-knob { transform: translateX(14px); }
.module-range { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light); }
.range-label { font-size: 11px; font-weight: 600; color: var(--text-muted); white-space: nowrap; }
.range-btns { display: flex; gap: 3px; flex-wrap: wrap; }
.range-btn { padding: 4px 10px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.15s ease; }
.range-btn:hover { border-color: var(--accent-cyan); color: var(--text-secondary); }
.range-btn.active { background: rgba(0,212,255,0.1); border-color: rgba(0,212,255,0.4); color: var(--accent-cyan); }
.module-realtime { display: flex; align-items: center; gap: 6px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light); font-size: 11px; font-weight: 600; color: var(--accent-cyan); }
.data-note { display: flex; align-items: flex-start; gap: 6px; margin-top: 14px; padding: 10px 12px; border-radius: 6px; background: rgba(0,212,255,0.04); border: 1px solid rgba(0,212,255,0.1); font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.data-note svg { flex-shrink: 0; margin-top: 1px; color: var(--accent-cyan); }

.report-meta { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.meta-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.meta-tag { font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 6px; background: var(--tag-bg); color: var(--accent-cyan); border: 1px solid var(--tag-border); }
.meta-tag.severity { border: none; }
.report-summary { margin: 0; font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-width: 640px; }
.gen-btn {
  display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 8px;
  border: 1px solid rgba(0,212,255,0.3); background: rgba(0,212,255,0.08);
  color: var(--accent-cyan); font-size: 13px; font-weight: 600; cursor: pointer;
  transition: all 0.2s ease; white-space: nowrap; flex-shrink: 0;
}
.gen-btn:hover { background: rgba(0,212,255,0.15); border-color: var(--accent-cyan); box-shadow: var(--glow-cyan); }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi-card { padding: 14px; border-radius: var(--radius); background: var(--panel-bg); border: 1px solid var(--border-light); transition: all 0.2s ease; }
.kpi-card:hover { border-color: var(--border); background: var(--panel-hover); }
.kpi-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.kpi-label { font-size: 12px; font-weight: 600; color: var(--text-muted); }
.kpi-trend { display: flex; align-items: center; gap: 2px; font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.kpi-trend.up { color: var(--accent-green); } .kpi-trend.down { color: var(--accent-red); }
.kpi-value { font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 800; line-height: 1; margin-bottom: 10px; }
.kpi-value small { font-size: 14px; font-weight: 600; margin-left: 2px; opacity: 0.7; }
.kpi-bar { height: 3px; border-radius: 2px; background: rgba(148,163,184,0.1); overflow: hidden; }
.kpi-bar-fill { height: 100%; border-radius: 2px; transition: width 0.6s ease; }

.no-data-hint {
  display: flex; align-items: center; gap: 6px; padding: 8px 14px;
  border-radius: 8px; background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.15);
  font-size: 12px; font-weight: 500; color: var(--accent-amber);
}

.chart-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.chart-card { border-radius: var(--radius); background: var(--panel-bg); border: 1px solid var(--border-light); padding: 14px; transition: all 0.2s ease; }
.chart-card:hover { border-color: var(--border); }
.chart-card.span-2 { grid-column: span 2; }
.chart-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); margin-bottom: 8px; letter-spacing: 0.02em; }
.chart-container { width: 100%; height: 220px; }
.chart-card.span-2 .chart-container { height: 200px; }

.chart-empty {
  width: 100%; height: 200px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px;
  animation: fadeIn 0.4s ease;
}
.chart-card.span-2 .chart-empty { height: 160px; }
.empty-icon { color: var(--text-muted); opacity: 0.35; animation: emptyFloat 3s ease-in-out infinite; }
@keyframes emptyFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
.empty-title { margin: 0; font-size: 14px; font-weight: 600; color: var(--text-muted); }
.empty-desc { margin: 0; font-size: 11px; color: var(--text-muted); opacity: 0.6; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.text-empty {
  display: flex; align-items: center; gap: 6px; padding: 8px 12px;
  border-radius: 6px; background: var(--item-bg); color: var(--text-muted);
  font-size: 13px; font-weight: 500;
}

.wallpaper-rows { display: flex; flex-direction: column; gap: 12px; }
.wallpaper-row { display: grid; grid-template-columns: 1fr 200px 52px; gap: 12px; align-items: center; }
.wallpaper-info strong { display: block; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.wallpaper-info span { font-size: 11px; color: var(--text-muted); }
.wallpaper-bar { height: 6px; border-radius: 3px; background: rgba(148,163,184,0.1); overflow: hidden; }
.wallpaper-bar-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green)); transition: width 0.6s ease; }
.wallpaper-rate { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; color: var(--accent-green); text-align: right; }

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
.file-dist-bar { height: 6px; border-radius: 3px; background: rgba(148,163,184,0.1); overflow: hidden; position: relative; }
.file-dist-bar-success { height: 100%; border-radius: 3px; background: var(--accent-green); position: absolute; left: 0; top: 0; }
.file-dist-bar-failed { height: 100%; background: var(--accent-red); position: absolute; top: 0; }

.attention-list { display: flex; flex-direction: column; gap: 8px; }
.attention-row { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; border-radius: 8px; background: var(--item-bg); transition: background 0.2s ease; }
.attention-row:hover { background: var(--item-hover); }
.attention-level { flex-shrink: 0; display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 6px; margin-top: 1px; }
.attention-level.warning { color: var(--accent-red); background: rgba(239,68,68,0.1); }
.attention-level.attention { color: var(--accent-amber); background: rgba(245,158,11,0.1); }
.attention-level.normal { color: var(--accent-green); background: rgba(34,197,94,0.1); }
.attention-info strong { display: block; font-size: 12px; font-weight: 600; color: var(--text-primary); line-height: 1.4; }
.attention-info small { font-size: 11px; color: var(--text-muted); }

.panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.panel-header h3 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }

.text-report { padding: 22px; }
.text-report-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.section-label { margin: 0; color: var(--text-muted); font-size: 12px; font-weight: 700; }
.text-report-header h2 { margin: 4px 0 0; font-size: 20px; font-weight: 800; color: var(--text-primary); }
.lead-text { margin: 0; border-left: 4px solid var(--accent-cyan); border-radius: 0 8px 8px 0; background: var(--tag-bg); font-size: 14px; line-height: 1.8; padding: 12px 14px; color: var(--text-secondary); }
.report-section { border-top: 1px solid var(--border-light); margin-top: 18px; padding-top: 16px; }
.report-section h4 { margin: 0 0 10px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.report-section ul { display: grid; gap: 8px; margin: 0; padding-left: 20px; color: var(--text-secondary); font-size: 14px; line-height: 1.8; }

@media (max-width: 1200px) {
  .chart-grid { grid-template-columns: 1fr; }
  .chart-card.span-2 { grid-column: span 1; }
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .module-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .sidebar-left { display: none; }
  .kpi-row { grid-template-columns: 1fr 1fr; }
  .dash-header { flex-wrap: wrap; gap: 8px; }
  .header-center { order: -1; width: 100%; justify-content: center; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; animation-iter-count: 1 !important; }
}
</style>
