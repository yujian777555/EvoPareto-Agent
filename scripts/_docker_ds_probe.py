import json
import os
import urllib.request

key = os.environ["DEEPSEEK_API_KEY"]
body = json.dumps({
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 8,
    "thinking": {"type": "disabled"},
}).encode()
req = urllib.request.Request(
    "https://api.deepseek.com/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
)
try:
    r = urllib.request.urlopen(req, timeout=25)
    d = r.read()
    print("status", r.status, "len", len(d))
    print(d[:300])
except Exception as e:
    print("ERR", type(e).__name__, e)
