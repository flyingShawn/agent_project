import urllib.request, json

r1 = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/desk-agent/conversations?user_id=admin')
d1 = json.loads(r1.read().decode())

r2 = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ticket-agent/conversations?user_id=admin')
d2 = json.loads(r2.read().decode())

print(f"desk-agent conversations: {d1['total']}")
print(f"ticket-agent conversations: {d2['total']}")
print(f"\ndesk-agent titles: {[c['title'] for c in d1['items'][:5]]}")
print(f"ticket-agent titles: {[c['title'] for c in d2['items'][:5]]}")
