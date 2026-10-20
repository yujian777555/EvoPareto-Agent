# CLEANUP_FN_EXCEPTION Secondary TypeError Fix (Task A)

When `docker rm` succeeded (`error` remained `None`), the cleanup_fn exception
handler attempted string concatenation on `None`, raising `TypeError` and
masking the real cleanup failure.

Fix: `prev = cleanup_status.get("error") or ""` before concatenation. All
three paths (normal exit / no-cid / Popen failure) now correctly record
`CLEANUP_FN_EXCEPTION`, set `cleaned=False`, and preserve the original error
context alongside the callback failure.

| Scenario | cleaned | error recorded | ok |
|---|---|---|---|
| rm ok + callback ok | True | (none) | True |
| rm ok + callback raises | False | CLEANUP_FN_EXCEPTION | False |
| rm fails + callback raises | False | DOCKER_RM_FAILED + CLEANUP_FN_EXCEPTION | False |
| Popen fails + callback raises | False | POPEN_FAILED + CLEANUP_FN_EXCEPTION | False |
