import http.client
import json
import os
import ssl
import time

for k in list(os.environ):
    if "proxy" in k.lower():
        del os.environ[k]

key = os.environ["DEEPSEEK_API_KEY"]
payload = {
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 8,
}
body = json.dumps(payload)
print("body", body)

ctx = ssl.create_default_context()
conn = http.client.HTTPSConnection("api.deepseek.com", 443, timeout=30, context=ctx)
t0 = time.time()
conn.request(
    "POST",
    "/v1/chat/completions",
    body=body,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "EvoPareto-Agent/1.0",
        "Connection": "close",
    },
)
try:
    resp = conn.getresponse()
    data = resp.read()
    print("status", resp.status, "time", round(time.time() - t0, 2), "nbytes", len(data))
    print(data[:500])
except Exception as e:
    print("ERR", type(e).__name__, e, "time", round(time.time() - t0, 2))
