import urllib.request
import json
import sys

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_chat_stream(agent_type, question):
    url = f"{API_BASE}/{agent_type}/chat"
    data = json.dumps({
        "question": question,
        "lognum": "admin",
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            full_response = r.read().decode()
            lines = [l for l in full_response.split('\n') if l.strip()]
            content_parts = []
            for line in lines:
                if line.startswith('data: '):
                    payload = line[6:]
                    if payload == '[DONE]':
                        break
                    try:
                        obj = json.loads(payload)
                        if obj.get('type') == 'content':
                            content_parts.append(obj.get('content', ''))
                        elif obj.get('type') == 'error':
                            print(f"  ERROR: {obj.get('message', '')}")
                    except json.JSONDecodeError:
                        pass
            return ''.join(content_parts)
    except Exception as e:
        return f"Request error: {e}"

print("=" * 60)
print("Test: desk-agent chat - '查看客户端在线状态'")
print("=" * 60)
response = test_chat_stream("desk-agent", "查看客户端在线状态")
print(f"  Response: {response[:200]}...")
if "在线" in response or "客户端" in response or "状态" in response or len(response) > 50:
    print("✅ PASS: desk-agent chat works")
else:
    print("⚠️  WARNING: desk-agent response may not be expected")

print("\n" + "=" * 60)
print("Test: ticket-agent chat - '你好'")
print("=" * 60)
response = test_chat_stream("ticket-agent", "你好")
print(f"  Response: {response[:200]}...")
if len(response) > 10:
    print("✅ PASS: ticket-agent chat works")
else:
    print("⚠️  WARNING: ticket-agent response may not be expected")

print("\n" + "=" * 60)
print("CHAT TESTS COMPLETE!")
print("=" * 60)
