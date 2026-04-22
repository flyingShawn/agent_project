// 本地开发时统一从仓库根目录 .env 读取 VITE_* 配置。
// Docker 部署时，容器启动脚本会覆盖这个文件并注入运行时配置。
window.__APP_CONFIG__ = {};
