"""
系统诊断脚本 - 检查所有依赖服务
"""
import json
import socket
import urllib.request
import urllib.error
import os
import sys
from pathlib import Path

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_port(host, port):
    """检查端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def check_http(url):
    """检查 HTTP 服务是否响应"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True, resp.status, resp.read(200).decode('utf-8', errors='ignore')[:200]
    except urllib.error.URLError as e:
        return False, str(e), ""
    except Exception as e:
        return False, str(e), ""

def load_env():
    """加载 .env 文件"""
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        print("⚠️  .env 文件不存在")
        return {}

    env_vars = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    return env_vars

def main():
    print_header("桌管智能体系统诊断")

    # 检查 Python 环境
    print(f"\n✅ Python 版本: {sys.version.split()[0]}")

    # 加载配置
    print_header("配置文件检查")
    env = load_env()
    if env:
        print("✅ .env 文件已加载")
        print(f"   - CHAT_MODEL: {env.get('CHAT_MODEL', '未设置')}")
        print(f"   - OLLAMA_BASE_URL: {env.get('OLLAMA_BASE_URL', '未设置')}")
        print(f"   - DATABASE_URL: {'已设置' if env.get('DATABASE_URL') else '未设置（将使用分开的配置）'}")
        print(f"   - DB_HOST: {env.get('DB_HOST', '未设置')}")
        print(f"   - RAG_QDRANT_URL: {env.get('RAG_QDRANT_URL', '未设置')}")
    else:
        print("⚠️  .env 文件未找到或为空")

    # 检查端口
    print_header("端口检查")

    services = [
        ("Ollama", "localhost", 11434),
        ("后端API", "localhost", 8000),
        ("前端", "localhost", 3000),
        ("Qdrant", "localhost", 6333),
    ]

    for name, host, port in services:
        if check_port(host, port):
            print(f"✅ {name} (http://{host}:{port}) - 端口开放")
        else:
            print(f"❌ {name} (http://{host}:{port}) - 端口未开放")

    # 检查 HTTP 服务
    print_header("HTTP 服务检查")

    endpoints = [
        ("Ollama API", "http://localhost:11434/api/version"),
        ("后端健康检查", "http://localhost:8000/api/v1/health"),
        ("前端页面", "http://localhost:3000"),
    ]

    for name, url in endpoints:
        try:
            success, status, body = check_http(url)
            if success:
                print(f"✅ {name} - 正常 (状态码: {status})")
                if "AI" in body or "chat" in body.lower() or "version" in body:
                    print(f"   内容预览: {body[:100]}...")
            else:
                print(f"❌ {name} - 失败: {status}")
        except Exception as e:
            print(f"❌ {name} - 错误: {e}")

    # 检查 Python 依赖
    print_header("Python 依赖检查")
    required_modules = [
        "fastapi", "uvicorn", "pydantic", "sqlalchemy",
        "qdrant_client", "langchain", "llama_index"
    ]
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError:
            print(f"❌ {module} - 未安装")

    # 检查模型
    print_header("Ollama 模型检查")
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = data.get('models', [])
            if models:
                print(f"✅ 已安装 {len(models)} 个模型:")
                for m in models:
                    print(f"   - {m.get('name', '未知')}")
            else:
                print("⚠️  没有安装任何模型")
    except Exception as e:
        print(f"❌ 无法获取模型列表: {e}")

    # 总结
    print_header("诊断总结")
    print("""
请根据以上检查结果：

1. 如果 Ollama 端口未开放：
   - 运行 'ollama serve' 启动 Ollama 服务

2. 如果后端端口未开放：
   - 运行 'python -m uvicorn agent_backend.main:app --reload' 启动后端

3. 如果前端端口未开放：
   - 进入 agent_frontend 目录
   - 运行 'npm install' 安装依赖
   - 运行 'npm run dev' 启动前端

4. 如果没有安装模型：
   - 运行 'ollama pull qwen3:14b'
   - 运行 'ollama pull qwen3.5:9b'（用于视觉）

5. 启动顺序建议：
   1) ollama serve
   2) python -m uvicorn agent_backend.main:app --reload
   3) cd agent_frontend && npm run dev
""")

if __name__ == "__main__":
    main()
