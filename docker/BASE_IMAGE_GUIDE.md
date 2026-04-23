# 后端基础镜像构建指南

## 概述

后端 Docker 构建采用**分层镜像**策略，将耗时的依赖安装与代码复制分离：

| 镜像 | Dockerfile | 内容 | 重建时机 |
|------|-----------|------|---------|
| `agent-backend-base:latest` | `Dockerfile.backend.base` | 系统依赖 + pip install + fastembed 模型 | 仅当 `requirements.txt` 变更时 |
| `agent-backend:latest` | `Dockerfile.backend` | 基于 base 镜像，仅复制项目代码 | 代码变更时（秒级完成） |

## 快速开始

### 首次部署

```bash
# 第一步：构建基础镜像（耗时约 5-10 分钟）
# Windows:
powershell -File docker/build-base.ps1
# Linux/Mac:
bash docker/build-base.sh

# 第二步：构建并启动所有服务（后端构建秒级完成）
docker compose up -d --build
```

### 日常开发（仅代码变更）

```bash
# 直接构建并启动，后端构建只需几秒
docker compose up -d --build
```

## 何时需要重建基础镜像

以下情况**必须**重建基础镜像：

1. **`requirements.txt` 发生变更** — 新增、删除、升级了 Python 依赖包
2. **Python 基础镜像版本变更** — 修改了 `Dockerfile.backend.base` 中的 `FROM python:3.11-slim`
3. **系统依赖变更** — 修改了 `apt-get install` 的包列表
4. **fastembed 模型变更** — 修改了 `RAG_EMBEDDING_MODEL` 对应的模型名称

重建命令：

```bash
# Windows:
powershell -File docker/build-base.ps1
# Linux/Mac:
bash docker/build-base.sh
# 或直接:
docker build -f docker/Dockerfile.backend.base -t agent-backend-base:latest .
```

## 文件说明

```
docker/
├── Dockerfile.backend.base   ← 基础镜像（依赖层，不常变）
├── Dockerfile.backend        ← 应用镜像（代码层，频繁变更）
├── build-base.ps1            ← Windows 一键构建基础镜像脚本
├── build-base.sh             ← Linux/Mac 一键构建基础镜像脚本
└── BASE_IMAGE_GUIDE.md       ← 本文档
```

## 注意事项

1. **基础镜像必须先存在** — `Dockerfile.backend` 的 `FROM agent-backend-base:latest` 要求本地已有该镜像，否则构建失败。首次部署或换机器时，务必先构建基础镜像。

2. **`docker compose build` 不会自动重建基础镜像** — 它只会基于现有的 `agent-backend-base:latest` 构建应用镜像。如果依赖变更了，需要手动执行基础镜像构建。

3. **清理旧镜像** — 重建基础镜像后，旧镜像会变成 `<none>` 标签，可用以下命令清理：
   ```bash
   docker image prune
   ```

4. **跨机器部署** — 新机器首次部署有两种方式：
   - **方式一**：在新机器上构建基础镜像（需要网络下载依赖）
   - **方式二**：导出/导入基础镜像（离线部署）
     ```bash
     # 源机器导出
     docker save agent-backend-base:latest -o agent-backend-base.tar
     # 目标机器导入
     docker load -i agent-backend-base.tar
     ```

5. **回退到单阶段构建** — 如果需要恢复为原来的单 Dockerfile 构建方式，将 `Dockerfile.backend` 的内容替换为 `Dockerfile.backend.base` 的全部内容，再加上代码复制和启动命令即可。
