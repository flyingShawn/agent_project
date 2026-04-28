# 后端基础镜像构建指南

## 概述

后端 Docker 构建采用**分层镜像**策略，将耗时的依赖安装与代码复制分离：

| 镜像 | Dockerfile | 内容 | 重建时机 |
|------|-----------|------|---------|
| `agent-backend-base:latest` | `Dockerfile.backend.base` | 系统依赖 + pip install（不含docling）+ fastembed 模型 | 仅当 `requirements.txt` 变更时 |
| `agent-backend:latest` | `Dockerfile.backend` | 基于 base 镜像，仅复制项目代码 | 代码变更时（秒级完成） |
| `agent-docling-sync-base:latest` | `Dockerfile.docling-sync.base` | 系统依赖 + pip install（含docling+torch）+ fastembed 模型 | 仅当 `requirements-docling.txt` 变更时 |
| `agent-docling-sync:latest` | `Dockerfile.docling-sync` | 基于 sync-base 镜像，仅复制项目代码 | 代码变更时（秒级完成） |

### 架构说明

主 API 镜像（`agent-backend`）不含 docling/torch 等重量级 ML 依赖，常驻运行时体积约 2-3GB。
文档同步镜像（`agent-docling-sync`）包含 docling + torch，仅在同步文档时按需启动，完成后自动退出。
GPU 资源在 99.9% 的时间释放给 Ollama 使用。

## 快速开始

### 首次部署

```bash
# 第一步：构建主API基础镜像（约 3-5 分钟）
# Windows:
powershell -File docker/build-base.ps1
# Linux/Mac:
bash docker/build-base.sh

# 第二步：构建并启动所有服务（后端构建秒级完成）
docker compose up -d --build
```

### 同步文档知识库

```bash
# 第一步：构建文档同步基础镜像（约 10-20 分钟，仅首次需要）
# Windows (CPU版):
powershell -File docker/build-docling-sync.ps1
# Windows (GPU版，需要NVIDIA Container Toolkit):
powershell -File docker/build-docling-sync.ps1 --gpu
# Linux/Mac (CPU版):
bash docker/build-docling-sync.sh
# Linux/Mac (GPU版):
bash docker/build-docling-sync.sh --gpu

# 第二步：启动文档同步（完成后容器自动退出）
.\scripts\sync.cmd docs
```

### 日常开发（仅代码变更）

```bash
# 直接构建并启动，后端构建只需几秒
docker compose up -d --build
```

## 何时需要重建基础镜像

### 主 API 基础镜像

以下情况**必须**重建：

1. **`requirements.txt` 发生变更** — 新增、删除、升级了 Python 依赖包
2. **Python 基础镜像版本变更** — 修改了 `FROM python:3.11-slim`
3. **系统依赖变更** — 修改了 `apt-get install` 的包列表
4. **fastembed 模型变更** — 修改了 `RAG_EMBEDDING_MODEL` 对应的模型名称

重建命令：

```bash
# Windows:
powershell -File docker/build-base.ps1
# Linux/Mac:
bash docker/build-base.sh
```

### 文档同步基础镜像

以下情况**必须**重建：

1. **`requirements-docling.txt` 发生变更** — docling 版本更新
2. **torch 版本切换** — 从 CPU 切换到 GPU 或反之

重建命令：

```bash
# CPU版（默认，镜像约 4-5GB）:
powershell -File docker/build-docling-sync.ps1
# GPU版（需要NVIDIA Container Toolkit，镜像约 10GB）:
powershell -File docker/build-docling-sync.ps1 --gpu
```

## 文件说明

```
docker/
├── Dockerfile.backend.base       ← 主API基础镜像（依赖层，不含docling）
├── Dockerfile.backend            ← 主API应用镜像（代码层）
├── Dockerfile.docling-sync.base  ← 文档同步基础镜像（含docling+torch）
├── Dockerfile.docling-sync       ← 文档同步应用镜像（代码层）
├── build-base.ps1                ← Windows 构建主API基础镜像
├── build-base.sh                 ← Linux/Mac 构建主API基础镜像
├── build-docling-sync.ps1        ← Windows 构建文档同步基础镜像
├── build-docling-sync.sh         ← Linux/Mac 构建文档同步基础镜像
└── BASE_IMAGE_GUIDE.md           ← 本文档
```

## 依赖文件说明

```
requirements.txt            ← 主API依赖（不含docling/playwright）
requirements-docling.txt    ← 文档同步依赖（继承requirements.txt + docling）
```

## 注意事项

1. **基础镜像必须先存在** — `Dockerfile.backend` 的 `FROM agent-backend-base:latest` 要求本地已有该镜像，否则构建失败。首次部署或换机器时，务必先构建基础镜像。

2. **`docker compose build` 不会自动重建基础镜像** — 它只会基于现有的基础镜像构建应用镜像。如果依赖变更了，需要手动执行基础镜像构建。

3. **文档同步服务不默认启动** — 使用 `profiles: ["docling"]` 控制，需要时通过 `docker compose --profile docling up docling-sync` 启动。

4. **清理旧镜像** — 重建基础镜像后，旧镜像会变成 `<none>` 标签，可用以下命令清理：
   ```bash
   docker image prune
   ```

5. **跨机器部署** — 新机器首次部署有两种方式：
   - **方式一**：在新机器上构建基础镜像（需要网络下载依赖）
   - **方式二**：导出/导入基础镜像（离线部署）
     ```bash
     # 源机器导出
     docker save agent-backend-base:latest -o agent-backend-base.tar
     docker save agent-docling-sync-base:latest -o agent-docling-sync-base.tar
     # 目标机器导入
     docker load -i agent-backend-base.tar
     docker load -i agent-docling-sync-base.tar
     ```

6. **GPU 支持** — 文档同步镜像支持 GPU 加速（需安装 NVIDIA Container Toolkit）：
   - 构建时加 `--gpu` 参数安装 CUDA 版 torch
   - docker-compose.yml 中 docling-sync 服务已预留 GPU 设备映射配置（默认注释）
