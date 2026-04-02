# 桌管智能体项目

> 为老C++桌面管理系统开发的智能Agent助手，提供自然语言"知识文档问答"及"数据库只读数据智能查询"功能。

## 📚 文档导航

所有详细文档都在 `help/` 目录下：

### 🚀 快速开始
- **[快速测试指南](help/快速测试指南.md)** - ⭐ 5分钟快速测试（推荐）
- **[测试运行指南](help/测试运行指南.md)** - 本地测试和Docker部署的完整指南
- **[项目检查报告](help/项目检查报告.md)** - 项目状态和检查结果

### ⚙️ 配置说明
- **[配置文件说明](help/配置文件说明.md)** - 所有配置项的详细说明
- **[数据库配置指南](help/数据库配置指南.md)** - 数据库连接配置方法

### 📋 项目文档
- **[需求文档](help/task.md)** - 项目需求和技术方案

## 🛠️ 快速配置

### 1. 配置环境

```bash
# 复制配置文件
copy .env.example .env

# 编辑配置文件
notepad .env
```

### 2. 配置数据库

在 `.env` 文件中配置数据库连接：

```bash
# 数据库类型
DB_TYPE=mysql

# 连接信息
DB_HOST=localhost
DB_PORT=3306
DB_NAME=your_database
DB_USER=root
DB_PASSWORD=your_password
```

### 3. 配置模型

在 `.env` 文件中配置模型：

```bash
# 文本模型
CHAT_MODEL=qwen2.5:7b

# 视觉模型
VISION_MODEL=qwen2.5-vl:7b
```

### 4. 验证配置

```bash
# 运行配置检查
检查配置.bat
```

## 🚀 快速启动

### 本地测试

```bash
# 1. 启动Ollama
ollama serve

# 2. 下载模型（首次需要）
ollama pull qwen2.5:7b
ollama pull qwen2.5-vl:7b

# 3. 启动后端
python -m uvicorn agent_backend.main:app --reload

# 4. 启动前端
cd agent_frontend
npm install
npm run dev
```

### Docker部署

```bash
# 一键部署
docker\deploy.bat
```

## 📁 项目结构

```
desk-agent-project/
├── agent_backend/      # 后端代码
│   ├── api/           # API路由
│   ├── core/          # 核心模块
│   ├── sql_agent/     # SQL智能查询
│   ├── rag_engine/    # RAG文档问答
│   └── llm/           # 大模型客户端
├── agent_frontend/     # 前端代码
├── docker/            # Docker配置
├── help/              # 项目文档
├── data/              # 数据目录
├── scripts/           # 工具脚本
└── tests/             # 测试代码
```

## 🛠️ 工具脚本

- `快速测试.bat` - 快速测试环境和配置
- `检查配置.bat` - 检查配置状态
- `scripts/测试数据库连接.py` - 测试数据库连接

## 📖 详细文档

请查看 `help/` 目录下的详细文档：

1. **测试运行指南.md** - 完整的测试和部署指南
2. **配置文件说明.md** - 所有配置项的详细说明
3. **数据库配置指南.md** - 数据库连接配置方法
4. **项目检查报告.md** - 项目状态和检查结果

## 🔗 访问地址

启动服务后：

- **前端界面**：http://localhost:3000
- **API文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/api/v1/health

## 💡 提示

- 修改配置后重启服务即可生效，无需修改代码
- 所有配置都在 `.env` 文件中
- 使用 `检查配置.bat` 验证配置是否正确

---

**更多信息请查看 [help/](help/) 目录下的详细文档。**
