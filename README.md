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

# 或手动执行（V2版本）
docker compose build
docker compose up -d
```

## 📁 项目结构

```
desk-agent-project/
├── agent_backend/      # 后端代码
│   ├── api/           # API路由
│   ├── chat/          # 聊天核心模块
│   ├── core/          # 核心模块
│   ├── llm/           # 大模型客户端
│   ├── rag_engine/    # RAG文档问答引擎
│   │   ├── chunking.py      # 文档分块
│   │   ├── docling_parser.py # 文档解析
│   │   ├── embedding.py     # 文本向量化
│   │   ├── ingest.py        # 文档导入
│   │   ├── qdrant_store.py  # 向量数据库存储
│   │   ├── retrieval.py     # 混合检索
│   │   └── settings.py      # RAG配置
│   └── sql_agent/     # SQL智能查询
├── agent_frontend/     # 前端代码
├── data/              # 数据目录
│   └── docs/          # 知识库文档（用户上传）
├── docker/            # Docker配置
├── help/              # 项目文档
├── scripts/           # 工具脚本
└── tests/             # 测试代码
```

## 🛠️ 工具脚本

- `快速测试.bat` - 快速测试环境和配置
- `检查配置.bat` - 检查配置状态
- `scripts/测试数据库连接.py` - 测试数据库连接
- `scripts/smoke_demo.py` - 冒烟测试脚本

## 🧠 RAG 文档问答

系统支持基于知识库的文档问答功能：

### 支持的文档格式
- **Office 文档**: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx)
- **文本文件**: Markdown (.md), 纯文本 (.txt)
- **图片**: PNG, JPG, JPEG, WebP（支持 OCR 识别）

### 文档导入
```bash
# 将文档放入 data/docs/ 目录
cp your-document.pdf data/docs/

# 调用 API 同步文档
POST /api/v1/rag/sync
{
  "mode": "incremental"  # 或 "full" 全量同步
}
```

### RAG 技术架构
1. **文档解析**: 使用 Docling 将多种格式转换为 Markdown
2. **文档分块**: 按标题结构分块，支持重叠（默认 1800 字符，200 字符重叠）
3. **向量化**: 使用 BAAI/bge-m3 模型生成向量
4. **存储**: 使用 Qdrant 向量数据库存储
5. **检索**: 混合检索（向量相似度 + BM25 关键词匹配）

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

## ⚙️ 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DB_TYPE` | mysql | 数据库类型 (mysql/postgresql) |
| `DB_HOST` | localhost | 数据库主机 |
| `DB_PORT` | 3306 | 数据库端口 |
| `DB_NAME` | - | 数据库名 |
| `DB_USER` | - | 数据库用户名 |
| `DB_PASSWORD` | - | 数据库密码 |
| `CHAT_MODEL` | qwen2.5:7b | 聊天模型 |
| `VISION_MODEL` | qwen2.5-vl:7b | 视觉模型 |
| `RAG_EMBEDDING_MODEL` | BAAI/bge-m3 | Embedding 模型 |
| `RAG_QDRANT_URL` | http://localhost:6333 | Qdrant 服务地址 |

---

**更多信息请查看 [help/](help/) 目录下的详细文档。**
