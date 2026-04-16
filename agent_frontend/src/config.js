const defaultConfig = {
  appName: '阳途智能助手',
  subtitle: '阳途智能助手为您服务',
  welcomeText: '有什么我能帮您的呢？',
  inputPlaceholder: '给智能助手发消息',
  quickOptions: [
    '查看客户端在线状态',
    '今日远程操作记录',
    '近期开关机日志',
    '老旧资产设备查询',
    '部门设备数量统计',
    'USB使用记录查询',
  ],
}

const runtimeConfig = window.__APP_CONFIG__ || {}

const parseQuickOptions = (val) => {
  if (Array.isArray(val)) return val
  if (typeof val === 'string' && val.trim()) return val.split(',').map((s) => s.trim()).filter(Boolean)
  return null
}

const envConfig = {
  appName: import.meta.env.VITE_APP_NAME || null,
  subtitle: import.meta.env.VITE_APP_SUBTITLE || null,
  welcomeText: import.meta.env.VITE_APP_WELCOME_TEXT || null,
  inputPlaceholder: import.meta.env.VITE_APP_INPUT_PLACEHOLDER || null,
  quickOptions: parseQuickOptions(import.meta.env.VITE_QUICK_OPTIONS || ''),
}

const config = {
  appName: runtimeConfig.appName || envConfig.appName || defaultConfig.appName,
  subtitle: runtimeConfig.subtitle || envConfig.subtitle || defaultConfig.subtitle,
  welcomeText: runtimeConfig.welcomeText || envConfig.welcomeText || defaultConfig.welcomeText,
  inputPlaceholder: runtimeConfig.inputPlaceholder || envConfig.inputPlaceholder || defaultConfig.inputPlaceholder,
  quickOptions: runtimeConfig.quickOptions || envConfig.quickOptions || defaultConfig.quickOptions,
}

export default config
