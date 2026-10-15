import json
import os
import subprocess
import tempfile
import time

for k in list(os.environ):
    if "proxy" in k.lower():
        del os.environ[k]

key = os.environ["DEEPSEEK_API_KEY"]
body = {
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 8,
}
tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
tf.write(json.dumps(body).encode("utf-8"))
tf.close()
print("body", open(tf.name, encoding="utf-8").read())

cmd = [
    "curl.exe", "--noproxy", "*", "-sS", "-m", "40",
    "-w", "\nHTTPCODE:%{http_code} TIME:%{time_total}",
    "-X", "POST", "https://api.deepseek.com/v1/chat/completions",
    "-H", "Content-Type: application/json",
    "-H", f"Authorization: Bearer {key}",
    "--data-binary", f"@{tf.name}",
]
t0 = time.time()
try:
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=50)
    print("elapsed", round(time.time() - t0, 2))
    print(out.decode("utf-8", errors="replace")[:800])
except subprocess.CalledProcessError as e:
    print("elapsed", round(time.time() - t0, 2))
    print("CPE", e.returncode, (e.output or b"")[:800])
