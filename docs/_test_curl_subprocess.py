import os
import subprocess
import tempfile

from pathlib import Path

proxy = "http://127.0.0.1:7897"
key = os.environ.get("DEEPSEEK_API_KEY", "")
body = b'{"model":"deepseek-chat","messages":[{"role":"user","content":"Say OK"}],"max_tokens":8}'
tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
tf.write(body)
tf.close()

curl = "curl.exe"
cmd = [
    curl, "-sS", "-m", "25", "-w", "\n%{http_code}",
    "-X", "POST", "https://api.deepseek.com/v1/chat/completions",
    "-x", proxy,
    "-H", "Content-Type: application/json",
    "-H", f"Authorization: Bearer {key}",
    "--data-binary", f"@{tf.name}",
]
print("cmd", cmd[:6], "...")
try:
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=30)
    print("RAW", out[:500])
except subprocess.CalledProcessError as e:
    print("CPE", e.returncode, e.output[:500] if e.output else None)
except Exception as e:
    print("ERR", type(e).__name__, e)
