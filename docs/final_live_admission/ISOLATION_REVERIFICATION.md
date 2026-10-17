# Isolation Re-verification (Task D)

## Linux symlink security tests (previously skipped on Windows)

Engine: Docker `python:3.10-slim` (Linux, `os.symlink` available)

{
  "SYMLINK_REQUEST": "PASS",
  "SYMLINK_RESPONSE": "PASS",
  "TRAVERSAL_ID": "PASS",
  "ATOMIC_EXCL": "PASS",
  "NO_GOLD_IN_TASK_JSON": "PASS"
}

Covers SYMLINK_REQUEST, SYMLINK_RESPONSE, TRAVERSAL_ID, ATOMIC_EXCL,
NO_GOLD_IN_TASK_JSON — all PASS.

## Gold cannot be read by the container

- `/work/task.json` keys: `['task_id','question']`
- gold never appears in the prompt or IPC payload
- trusted scorer is host-side only

## Offline fixture honesty

The offline mock uses a **fixed small GSM8K-style fixture**
(`src/benchmark/gsm8k_tasks.py`), explicitly labelled `OFFLINE_FIXTURE`. It is
**not** presented as the complete official GSM8K set.

Real pilot data path (frozen protocol `src/benchmark/gsm8k_protocol.py`):

```
official GSM8K train 0-19  -> search / selection
official GSM8K train 20-29 -> validation
official GSM8K test 0-19   -> final held-out (never selection)
```

At pilot start the official JSONL is loaded, task ids hashed
(`split_sha256`), and `selection_uses_official_test_set=false` is enforced.

## Frozen results

n_tracked_results_files = **324**
(before/after SHA-256 compared by `tests/frozen_guard.py` session guard)

## Docker IPC negative tests

`--network none`, O_NOFOLLOW, O_EXCL, ID allowlist — see
`results/final_live_admission/linux_ipc_security_tests.json` and
`tests/baseline_first/test_ipc_security.py`.
