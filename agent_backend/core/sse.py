import json


def sse_event(event: str, data: str | dict) -> str:
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    lines = data.split("\n")
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"
