"""Direct DeepSeek call, bypassing all proxies (curl --noproxy)."""

import json
import os
import subprocess
import tempfile
import time


def main() -> None:
    # Clear proxy envs for this process
    for k in list(os.environ):
        if "proxy" in k.lower():
            del os.environ[k]

    key = os.environ.get("DEEPSEEK_API_KEY", "")
    print("key_len", len(key))
    body = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 4,
    }
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tf.write(json.dumps(body).encode("utf-8"))
    tf.close()

    cmd = [
        "curl.exe",
        "--noproxy", "*",
        "-sS", "-m", "25",
        "-w", "\nHTTPCODE:%{http_code}",
        "-X", "POST",
        "https://api.deepseek.com/v1/chat/completions",
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {key}",
        "--data-binary", f"@{tf.name}",
    ]
    t0 = time.time()
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=30)
        print("elapsed", round(time.time() - t0, 2))
        print(out.decode("utf-8", errors="replace")[:500])
    except subprocess.CalledProcessError as e:
        print("elapsed", round(time.time() - t0, 2))
        print("CPE", e.returncode, (e.output or b"")[:500])
    except Exception as e:
        print("ERR", type(e).__name__, e, "elapsed", round(time.time() - t0, 2))


if __name__ == "__main__":
    main()
