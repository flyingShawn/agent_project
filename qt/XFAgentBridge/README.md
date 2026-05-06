# XFAgentBridge

XFAgentBridge 是浏览器本机任务接收端。前端在 `desk-agent` 任务提交时优先调用本机：

```text
http://127.0.0.1:17891/api/v1/tasks/execute
```

第一版只负责接收任务、记录 JSONL 日志并立即返回“任务已接收”，真实桌管处理逻辑保留在 `TaskProcessor` 中后续扩展。

## 依赖

- Qt 6.5.3+
- Qt Creator
- Qt 模块：Widgets、Network、HttpServer
- CMake 3.21+

如果 Kit 缺少 `Qt6::HttpServer`，请用 Qt Maintenance Tool 为同一 Qt 版本补装 Qt HTTP Server 模块。

## 构建

用 Qt Creator 打开本目录的 `CMakeLists.txt`，选择 Qt 6.5.3 Kit 后构建即可。

命令行示例：

```powershell
cmake -S qt/XFAgentBridge -B build/XFAgentBridge
cmake --build build/XFAgentBridge --config Release
```

## 接口

```http
GET /api/v1/health
POST /api/v1/tasks/execute
OPTIONS /api/v1/tasks/execute
```

服务只监听 `127.0.0.1`，默认端口 `17891`。配置和任务日志使用 `QStandardPaths::AppDataLocation`，可跨 Windows、Linux、macOS 使用。
