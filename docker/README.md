# Docker部署指南

## 📋 目录
1. [前置要求](#前置要求)
2. [快速开始](#快速开始)
3. [详细说明](#详细说明)
4. [常用命令](#常用命令)
5. [故障排查](#故障排查)
6. [生产环境建议](#生产环境建议)

---

## 前置要求

### Windows系统
1. **安装Docker Desktop**
   - 下载地址：https://www.docker.com/products/docker-desktop
   - 安装后启动Docker Desktop
   - 确保Docker正在运行（系统托盘有Docker图标）

2. **验证安装**
   ```powershell
   docker --version
   docker-compose --version
   ```

### Linux系统
1. **安装Docker**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install docker.io docker-compose-plugin

   # CentOS/RHEL
   sudo yum install docker docker-compose-plugin
   ```

2. **启动Docker服务**
   ```bash
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

3. **添加当前用户到docker组（可选，避免每次使用sudo）**
   ```bash
   sudo usermod -aG docker $USER
   # 重新登录后生效
   ```

---

## 快速开始

### 1. 准备环境变量文件
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，配置必要参数
# Windows: notepad .env
# Linux: nano .env
```

### 2. 启动所有服务
```bash
# 构建并启动所有服务（首次运行）
docker-compose up -d --build

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3. 访问应用
- **前端界面**：http://localhost
- **后端API文档**：http://localhost:8000/docs
- **Qdrant控制台**：http://localhost:6333/dashboard

### 4. 停止服务
```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷（清除所有数据）
docker-compose down -v
```

---

## 详细说明

### 项目结构
```
agent_project/
├── Dockerfile.backend       # 后端镜像构建文件
├── Dockerfile.frontend      # 前端镜像构建文件
├── docker-compose.yml       # 服务编排配置
├── nginx.conf               # Nginx配置文件
├── .dockerignore            # Docker构建忽略文件
├── .env                     # 环境变量配置
└── requirements.txt         # Python依赖
```

### 服务架构
```
┌─────────────┐
│   用户浏览器  │
└──────┬──────┘
       │ http://localhost
       ↓
┌─────────────┐
│   Frontend  │ (Nginx + Vue.js)
│   端口: 80   │
└──────┬──────┘
       │ /api/*
       ↓
┌─────────────┐
│   Backend   │ (FastAPI)
│   端口: 8000 │
└──────┬──────┘
       │
       ├──────────────┐
       ↓              ↓
┌─────────────┐  ┌─────────────┐
│   Qdrant    │  │   Ollama    │
│   端口: 6333 │  │  端口: 11434 │
└─────────────┘  └─────────────┘
```

### 环境变量说明

#### 必需配置
```bash
# Ollama模型配置
OLLAMA_BASE_URL=http://ollama:11434
CHAT_MODEL=qwen2.5:7b-instruct
VISION_MODEL=qwen2.5-vl:7b-instruct

# RAG配置
RAG_QDRANT_URL=http://qdrant:6333
RAG_QDRANT_COLLECTION=desk_agent_docs
```

#### 可选配置
```bash
# 数据库连接（如果需要查询真实数据库）
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# API认证token
CHAT_API_TOKEN=your_token_here
```

---

## 常用命令

### 服务管理
```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose stop

# 重启所有服务
docker-compose restart

# 重启单个服务
docker-compose restart backend

# 查看服务状态
docker-compose ps

# 查看资源使用情况
docker stats
```

### 日志查看
```bash
# 查看所有服务日志
docker-compose logs

# 实时查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs backend

# 查看最近100行日志
docker-compose logs --tail=100 backend
```

### 进入容器
```bash
# 进入后端容器
docker-compose exec backend bash

# 进入前端容器
docker-compose exec frontend sh

# 以root用户进入
docker-compose exec -u root backend bash
```

### 数据管理
```bash
# 查看数据卷
docker volume ls

# 查看数据卷详情
docker volume inspect agent_project_qdrant_data

# 备份数据卷
docker run --rm -v agent_project_qdrant_data:/data -v $(pwd):/backup alpine tar czf /backup/qdrant_backup.tar.gz /data

# 恢复数据卷
docker run --rm -v agent_project_qdrant_data:/data -v $(pwd):/backup alpine tar xzf /backup/qdrant_backup.tar.gz -C /
```

### 镜像管理
```bash
# 重新构建镜像
docker-compose build

# 强制重新构建（不使用缓存）
docker-compose build --no-cache

# 查看镜像
docker images

# 删除未使用的镜像
docker image prune
```

---

## 故障排查

### 1. 服务无法启动

**检查端口占用**
```bash
# Windows
netstat -ano | findstr :8000
netstat -ano | findstr :80

# Linux
netstat -tulpn | grep :8000
netstat -tulpn | grep :80
```

**解决方案**：
- 修改docker-compose.yml中的端口映射
- 停止占用端口的服务

### 2. 后端服务健康检查失败

**查看详细日志**
```bash
docker-compose logs backend
```

**常见原因**：
- Ollama服务未就绪（需要下载模型）
- Qdrant服务未启动
- 配置文件错误

**解决方案**：
```bash
# 重启后端服务
docker-compose restart backend

# 检查Ollama模型
docker-compose exec ollama ollama list
```

### 3. Ollama模型下载慢

**手动下载模型**
```bash
# 进入Ollama容器
docker-compose exec ollama bash

# 下载模型
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5-vl:7b-instruct
```

### 4. 前端无法访问后端API

**检查网络连接**
```bash
# 进入前端容器
docker-compose exec frontend sh

# 测试后端连接
wget -O- http://backend:8000/api/v1/health
```

**检查Nginx配置**
```bash
# 查看Nginx配置
docker-compose exec frontend cat /etc/nginx/conf.d/default.conf

# 测试Nginx配置
docker-compose exec frontend nginx -t
```

### 5. 数据丢失问题

**检查数据卷挂载**
```bash
docker-compose ps
docker volume ls
```

**解决方案**：
- 确保使用docker-compose.yml中定义的数据卷
- 不要使用`docker-compose down -v`（会删除数据卷）

---

## 生产环境建议

### 1. 安全加固

**修改默认端口**
```yaml
# docker-compose.yml
services:
  frontend:
    ports:
      - "8080:80"  # 改为非标准端口
```

**使用HTTPS**
```yaml
# 添加SSL证书
services:
  frontend:
    volumes:
      - ./ssl/cert.pem:/etc/nginx/ssl/cert.pem:ro
      - ./ssl/key.pem:/etc/nginx/ssl/key.pem:ro
```

### 2. 性能优化

**调整worker数量**
```dockerfile
# Dockerfile.backend
CMD ["uvicorn", "agent_backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**启用GPU加速**
```yaml
# docker-compose.yml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### 3. 监控和日志

**添加监控服务**
```yaml
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
```

**日志持久化**
```yaml
services:
  backend:
    volumes:
      - ./logs:/app/logs
```

### 4. 备份策略

**自动备份脚本**
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
docker run --rm \
  -v agent_project_qdrant_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/qdrant_$DATE.tar.gz /data
```

**定时任务（Linux crontab）**
```bash
# 每天凌晨2点备份
0 2 * * * /path/to/backup.sh
```

---

## 常见问题

### Q1: Docker Desktop启动慢
**A**: 增加Docker Desktop的内存和CPU配置
- 打开Docker Desktop设置
- Resources -> Memory: 建议8GB以上
- Resources -> CPUs: 建议4核以上

### Q2: 镜像构建失败
**A**: 检查网络连接，可能需要配置镜像加速器
```json
// Docker Desktop设置 -> Docker Engine
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn"
  ]
}
```

### Q3: 容器内无法访问宿主机服务
**A**: 使用特殊DNS名称
```bash
# Windows/Mac
host.docker.internal

# Linux（需要在docker-compose.yml中添加）
extra_hosts:
  - "host.docker.internal:host-gateway"
```

---

## 参考资源

- [Docker官方文档](https://docs.docker.com/)
- [Docker Compose官方文档](https://docs.docker.com/compose/)
- [FastAPI部署指南](https://fastapi.tiangolo.com/deployment/docker/)
- [Nginx配置指南](https://nginx.org/en/docs/)

---

## 技术支持

如遇到问题，请提供以下信息：
1. 操作系统版本
2. Docker版本 (`docker --version`)
3. Docker Compose版本 (`docker-compose --version`)
4. 错误日志 (`docker-compose logs`)
