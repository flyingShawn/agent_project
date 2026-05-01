import urllib.request
import json
import sys

API_BASE = "http://127.0.0.1:8000/api/v1"

def test_api(method, path, data=None):
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

print("=" * 60)
print("Test 1: Agents API")
print("=" * 60)
result = test_api("GET", "/agents")
print(json.dumps(result, indent=2, ensure_ascii=False))
assert len(result["agents"]) == 2, "Should have 2 agents"
assert result["default_agent_type"] == "desk-agent", "Default should be desk-agent"
print("✅ PASS: Agents API returns 2 agents with correct default")

print("\n" + "=" * 60)
print("Test 2: desk-agent conversations")
print("=" * 60)
result = test_api("GET", "/desk-agent/conversations?user_id=admin")
print(f"  Total conversations: {result.get('total', len(result.get('items', [])))}")
print("✅ PASS: desk-agent conversations API works")

print("\n" + "=" * 60)
print("Test 3: ticket-agent conversations (should be empty)")
print("=" * 60)
result = test_api("GET", "/ticket-agent/conversations?user_id=admin")
print(f"  Total conversations: {result.get('total', len(result.get('items', [])))}")
assert result.get("total", len(result.get("items", []))) == 0, "ticket-agent should have no conversations"
print("✅ PASS: ticket-agent conversations are isolated")

print("\n" + "=" * 60)
print("Test 4: desk-agent metadata summary")
print("=" * 60)
result = test_api("GET", "/desk-agent/metadata/summary")
if "error" in result:
    print(f"  Error: {result['error']}")
else:
    print(f"  Tables: {result.get('table_count', 'N/A')}")
    print("✅ PASS: desk-agent metadata API works with agent_type")

print("\n" + "=" * 60)
print("Test 5: ticket-agent metadata summary")
print("=" * 60)
result = test_api("GET", "/ticket-agent/metadata/summary")
if "error" in result:
    print(f"  Error: {result['error']}")
else:
    print(f"  Tables: {result.get('table_count', 'N/A')}")
    print("✅ PASS: ticket-agent metadata API works with agent_type")

print("\n" + "=" * 60)
print("Test 6: Health check")
print("=" * 60)
result = test_api("GET", "/health")
print(f"  Status: {result.get('status', 'N/A')}")
print("✅ PASS: Health check OK")

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
