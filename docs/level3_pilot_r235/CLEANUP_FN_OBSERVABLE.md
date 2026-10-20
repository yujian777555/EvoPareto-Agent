# Cleanup Callback Observability (Task B)

`cleanup_fn` exceptions are no longer silently swallowed.

| Path | Behaviour |
|---|---|
| normal container exit | `CLEANUP_FN_EXCEPTION` appended to `error`, `cleaned=False` |
| no container ID | same — `cleanup_fn` still runs, exceptions recorded |
| Popen failure | `cleanup_fn` runs, exceptions recorded |

Any cleanup failure sets `cleaned=False`, which blocks scoring
(`ok` requires `cleaned or not created`).

Three scenarios covered: normal exit, no-cid, Popen failure.
