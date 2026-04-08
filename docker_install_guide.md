# Docker安装指南（Linux服务器）

## Docker版本要求

根据项目的Docker配置文件分析，建议安装Docker 19.03或更高版本，以确保：

- 支持多阶段构建（前端Dockerfile使用）
- 支持健康检查指令
- 与Docker Compose版本兼容

## 通过yum安装Docker的步骤

### 1. 卸载旧版本的Docker（如果存在）

```bash
sudo yum remove docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine
```

### 2. 安装必要的依赖包

```bash
sudo yum install -y yum-utils device-mapper-persistent-data lvm2
```

### 3. 设置Docker的yum仓库

```bash
sudo yum-config-manager \
    --add-repo \
    http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo

sudo sed -i 's/\$releasever/8/g' /etc/yum.repos.d/docker-ce.repo

#sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
```

### 4. 安装Docker引擎

```bash
sudo yum install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

containerd.io问题
yum module reset container-tools -y
yum module reset docker -y
可以  
yum list containerd.io --showduplicates
前后查看

sudo yum clean all
sudo yum makecache
```

### 5. 启动Docker服务

```bash
sudo systemctl start docker
sudo systemctl enable docker
```

### 6. 验证Docker安装

```bash
sudo docker --version
sudo docker-compose --version
```

### 7. 配置非root用户使用Docker（可选）

```bash
sudo groupadd docker
sudo usermod -aG docker $USER
```

然后退出并重新登录，或者执行以下命令以立即生效：

```bash
newgrp docker
```

## 部署项目

安装完Docker后，您可以按照以下步骤部署项目：

1. 克隆项目代码到服务器
2. 进入项目目录
3. 启动服务：

```bash
docker-compose up -d
```

## 注意事项

- 项目使用了Ollama大模型服务，需要在Docker外部部署
- 对于Linux服务器，需要修改docker-compose.yml中的OLLAMA_BASE_URL，使用宿主机IP而不是host.docker.internal
- 确保服务器有足够的资源运行所有服务，特别是Qdrant向量数据库和Ollama大模型
