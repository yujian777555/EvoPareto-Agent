import os
import time

import requests

proxy = "http://127.0.0.1:7897"
proxies = {"http": proxy, "https": proxy}
key = os.environ.get("DEEPSEEK_API_KEY", "")
t0 = time.time()
try:
    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "Say OK"}],
            "max_tokens": 8,
        },
        proxies=proxies,
        timeout=30,
    )
    print("status", r.status_code, "time", round(time.time() - t0, 2))
    print(r.text[:400])
except Exception as e:
    print("ERR", type(e).__name__, e)
