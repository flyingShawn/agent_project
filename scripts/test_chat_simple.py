import urllib.request
import json
import sys

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_chat_simple(agent_type, question):
    url = f"{API_BASE}/{agent_type}/chat"
    data = json.dumps({
        "question": question,
        "lognum": "admin",
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
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

print("Testing desk-agent chat with simple question...")
response = test_chat_simple("desk-agent", "你好")
print(f"Response: {response[:300]}")
if len(response) > 5 and "error" not in response.lower():
    print("✅ PASS: desk-agent chat works!")
else:
    print("❌ FAIL: desk-agent chat failed")

print("\nTesting ticket-agent chat with simple question...")
response = test_chat_simple("ticket-agent", "你好")
print(f"Response: {response[:300]}")
if len(response) > 5 and "error" not in response.lower():
    print("✅ PASS: ticket-agent chat works!")
else:
    print("❌ FAIL: ticket-agent chat failed")
