import os
import subprocess
import tempfile
import time

key = os.environ.get("DEEPSEEK_API_KEY", "")
body = b'{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":4}'
tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
tf.write(body)
tf.close()

def try_curl(proxy=None, label=""):
    cmd = ["curl.exe", "-sS", "-m", "12", "-w", "\n%{http_code}", "-X", "POST",
           "https://api.deepseek.com/v1/chat/completions"]
    if proxy:
        cmd += ["-x", proxy]
    cmd += ["-H", "Content-Type: application/json",
            "-H", f"Authorization: Bearer {key}",
            "--data-binary", f"@{tf.name}"]
    t0 = time.time()
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=15)
        print(label, "OK", round(time.time()-t0, 2), out[:250])
    except subprocess.CalledProcessError as e:
        print(label, "CPE", round(time.time()-t0, 2), (e.output or b"")[:250])
    except Exception as e:
        print(label, "ERR", type(e).__name__, e)

try_curl(None, "direct")
try_curl("http://127.0.0.1:7897", "proxy7897")
