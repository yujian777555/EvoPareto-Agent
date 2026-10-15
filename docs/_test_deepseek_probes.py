import http.client
import json
import os
import ssl
import time

for k in list(os.environ):
    if "proxy" in k.lower():
        del os.environ[k]

key = os.environ["DEEPSEEK_API_KEY"]
ctx = ssl.create_default_context()

# Probe 1: missing auth -> expect fast 401
conn = http.client.HTTPSConnection("api.deepseek.com", 443, timeout=10, context=ctx)
t0 = time.time()
conn.request("POST", "/v1/chat/completions", body='{"model":"deepseek-flash","messages":[{"role":"user","content":"x"}]}',
             headers={"Content-Type": "application/json"})
try:
    r = conn.getresponse()
    print("noauth", r.status, round(time.time()-t0, 2), r.read()[:120])
except Exception as e:
    print("noauth ERR", e, round(time.time()-t0, 2))

# Probe 2: stream true, read first bytes
body = json.dumps({
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 8,
    "stream": True,
})
conn = http.client.HTTPSConnection("api.deepseek.com", 443, timeout=25, context=ctx)
t0 = time.time()
conn.request("POST", "/v1/chat/completions", body=body, headers={
    "Content-Type": "application/json",
    "Authorization": f"Bearer {key}",
    "Accept": "text/event-stream",
})
try:
    r = conn.getresponse()
    print("stream status", r.status, "time", round(time.time()-t0, 2))
    chunk = r.read(200)
    print("first200", chunk, "t", round(time.time()-t0, 2))
except Exception as e:
    print("stream ERR", type(e).__name__, e, round(time.time()-t0, 2))
