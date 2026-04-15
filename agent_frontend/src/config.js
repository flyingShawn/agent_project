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

const config = {
  appName: runtimeConfig.appName || defaultConfig.appName,
  subtitle: runtimeConfig.subtitle || defaultConfig.subtitle,
  welcomeText: runtimeConfig.welcomeText || defaultConfig.welcomeText,
  inputPlaceholder: runtimeConfig.inputPlaceholder || defaultConfig.inputPlaceholder,
  quickOptions: runtimeConfig.quickOptions || defaultConfig.quickOptions,
}

export default config
