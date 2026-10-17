# IPC Security Patch (Task 1)

**Gate A: PASS**

## Problem

`ModelIPCServer` used `rid = data.get("id") or req_path.stem` straight from
untrusted Workflow JSON to build the host response path. That allowed path
traversal / arbitrary host writes.

## Fix (`src/runtime/workflow_ipc.py`)

| Control | Mechanism |
|---|---|
| Request ID format | `^[0-9a-f]{32}$` only |
| JSON id must match filename | explicit compare, mismatch rejected |
| Path separators / `..` / drive letters | `_safe_join` rejects before any FS op |
| Response path source | **only** validated rid under `/ipc/in` — JSON fields ignored |
| Model / provider | trusted host config only; JSON `model` override rejected |
| Symlinks | `O_NOFOLLOW` on read and write |
| Overwrite | `O_EXCL` atomic create — never replace an existing response |
| Size caps | request 256 KiB, prompt 32 000 chars, backlog 64 |
| Duplicate ids | refused; second request never reaches the model |
| Security events | every rejection recorded (`security_events`) |

Validation happens **before** any model call. Illegal requests are deleted and
logged; `llm._request` is never invoked.

## Negative tests

`tests/baseline_first/test_ipc_security.py` covers TRAVERSAL_ID,
ABSOLUTE_PATH_ID, WINDOWS_PATH_ID, INVALID_ID, DUPLICATE_ID, SYMLINK_REQUEST,
SYMLINK_RESPONSE, OVERSIZED_REQUEST, REPLACED_FILE, UNAUTHORIZED_MODEL — all
rejected with zero model calls.

## TOCTOU note

Containment is checked lexically, then files are opened with `O_NOFOLLOW` +
`O_EXCL` so the validation/open race cannot retarget the path through a
symlink swap.
