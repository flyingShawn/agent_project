"""
测试聊天 API 的脚本
"""
import json
import urllib.request
import urllib.error


def test_chat_api(question: str, mode: str = "auto"):
    """测试聊天 API"""
    url = "http://localhost:8000/api/v1/chat"

    payload = {
        "question": question,
        "mode": mode,
        "lognum": "admin",
        "history": []
    }

    print(f"\n{'='*60}")
    print(f"测试问题: {question}")
    print(f"模式: {mode}")
    print(f"{'='*60}")

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        print("正在发送请求...")
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"状态码: {resp.status}")
            print(f"响应头: {dict(resp.headers)}")

            body = resp.read().decode("utf-8")
            print(f"\n响应内容 ({len(body)} 字符):")
            print("-" * 40)

            # 解析 SSE 事件
            lines = body.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("event:") or line.startswith("data:") or line == "":
                    print(line)

            print("-" * 40)

    except urllib.error.URLError as e:
        print(f"连接错误: {e}")
        print("后端服务可能没有启动，请先启动后端服务")
    except Exception as e:
        print(f"错误: {type(e).__name__}: {e}")


def test_health():
    """测试健康检查"""
    url = "http://localhost:8000/api/v1/health"
    print(f"\n测试健康检查: {url}")

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            print(f"状态码: {resp.status}")
            body = resp.read().decode("utf-8")
            print(f"响应: {body}")
    except urllib.error.URLError as e:
        print(f"连接错误: {e}")
        print("后端服务可能没有启动")


if __name__ == "__main__":
    print("=" * 60)
    print("聊天 API 测试工具")
    print("=" * 60)

    test_health()
    test_chat_api("你好", "rag")
    test_chat_api("一共有几个部门", "sql")
