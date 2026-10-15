import json
import os
import time
import urllib.request

proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "http://127.0.0.1:7897"
print("proxy", proxy)

# Force urllib to use the proxy
handler = urllib.request.ProxyHandler({
    "http": proxy,
    "https": proxy,
})
opener = urllib.request.build_opener(handler)
urllib.request.install_opener(opener)

key = os.environ.get("DEEPSEEK_API_KEY", "")
payload = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 8,
}
req = urllib.request.Request(
    "https://api.deepseek.com/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    },
    method="POST",
)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    print("OK", round(time.time() - t0, 2), body[:300])
except Exception as e:
    print("ERR", type(e).__name__, e)
