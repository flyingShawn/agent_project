# Docker部署Embedding模型加载失败问题分析与解决方案

## 问题诊断

### 错误信息分析

```
RuntimeError: Embedding 依赖不可用: ConnectError: [Errno 97] Address family not supported by protocol
```

**根本原因**：

1. FastEmbed在首次使用时会自动从HuggingFace下载模型文件
2. Docker容器在Linux服务器上无法访问HuggingFace（网络限制/防火墙）
3. 错误码`[Errno 97]`表明是网络协议族问题（IPv6/IPv4不兼容）

### 问题发生位置

* 文件：[embedding.py](file:///d:/work_space/agent_project/agent_backend/rag_engine/embedding.py#L66)

* 代码：`self._model = TextEmbedding(model_name=actual)`

* FastEmbed初始化时会调用HuggingFace Hub API下载模型

### 为什么本地开发没问题？

* 本地开发环境可以直接访问HuggingFace

* Docker容器内网络隔离，可能受服务器防火墙或网络策略限制

***

## 解决方案

### 方案一：构建时预下载模型（推荐）

**优点**：

* 模型打包到镜像中，运行时无需下载

* 部署简单，不依赖外部网络

* 启动速度快

**实施步骤**：

#### 1. 修改 `docker/Dockerfile.backend`

在安装Python依赖后，添加模型预下载步骤：

```dockerfile
# 安装Python依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 预下载Embedding模型（避免运行时下载）
# 设置HuggingFace镜像加速下载
ENV HF_ENDPOINT=https://hf-mirror.com
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')"
```

#### 2. 设置HuggingFace缓存目录（可选但推荐）

在Dockerfile中添加：

```dockerfile
# 设置模型缓存目录
ENV HF_HOME=/app/.cache/huggingface
ENV FASTEMBED_CACHE=/app/.cache/fastembed
```

在docker-compose.yml中添加持久化：

```yaml
volumes:
  # 持久化模型缓存
  - model_cache:/app/.cache
```

***

### 方案二：配置HuggingFace镜像站

**优点**：

* 不需要重新构建镜像

* 适合模型需要更新的场景

**实施步骤**：

#### 1. 修改 `docker-compose.yml`

在backend服务的environment中添加：

```yaml
environment:
  # HuggingFace镜像加速
  - HF_ENDPOINT=https://hf-mirror.com
  - HF_HOME=/app/.cache/huggingface
  - FASTEMBED_CACHE=/app/.cache/fastembed
```

#### 2. 添加缓存持久化

```yaml
volumes:
  - model_cache:/app/.cache

volumes:
  model_cache:
    driver: local
```

***

### 方案三：挂载本地模型文件

**优点**：

* 完全离线部署

* 模型文件可控

**实施步骤**：

#### 1. 在宿主机下载模型

```bash
# 在宿主机上执行
pip install fastembed
python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')"
```

#### 2. 找到模型缓存位置

默认位置：

* Linux: `~/.cache/huggingface/hub/` 或 `~/.cache/fastembed/`

* 查看环境变量：`echo $HF_HOME`

#### 3. 修改 `docker-compose.yml`

```yaml
volumes:
  # 挂载本地模型缓存
  - ~/.cache/fastembed:/app/.cache/fastembed:ro
  - ~/.cache/huggingface:/app/.cache/huggingface:ro
```

***

## 推荐实施方案

**最佳方案**：方案一（构建时预下载）+ 方案二（镜像加速）

完整修改内容：

### 1. 修改 `docker/Dockerfile.backend`

```dockerfile
# 安装Python依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 设置HuggingFace镜像和缓存目录
ENV HF_ENDPOINT=https://hf-mirror.com \
    HF_HOME=/app/.cache/huggingface \
    FASTEMBED_CACHE=/app/.cache/fastembed

# 预下载Embedding模型
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')"
```

### 2. 修改 `docker-compose.yml`

```yaml
services:
  backend:
    # ... 其他配置 ...
    environment:
      # ... 现有环境变量 ...
      # HuggingFace配置
      - HF_ENDPOINT=https://hf-mirror.com
      - HF_HOME=/app/.cache/huggingface
      - FASTEMBED_CACHE=/app/.cache/fastembed
    volumes:
      # ... 现有挂载 ...
      # 持久化模型缓存
      - model_cache:/app/.cache

volumes:
  # ... 现有卷 ...
  model_cache:
    driver: local
```

### 3. 重新构建和部署

```bash
# 重新构建镜像
docker compose build backend

# 重启服务
docker compose up -d
```

***

## 验证步骤

1. 检查构建日志，确认模型下载成功
2. 查看容器日志：`docker logs desk-agent-backend`
3. 测试聊天功能，确认无错误

***

## 补充说明

### 关于模型大小

* `BAAI/bge-small-zh-v1.5`: 约100MB

* `BAAI/bge-m3`: 约2GB

### 网络问题排查

如果镜像站也无法访问，可以：

1. 在有网络的机器上下载模型
2. 通过U盘或其他方式拷贝到服务器
3. 使用方案三挂载本地模型

### 其他注意事项

* 确保服务器有足够的磁盘空间（至少5GB用于模型和缓存）

* 如果使用代理，需要配置HTTP\_PROXY环境变量

