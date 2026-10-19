# Docker Startup & Cleanup Exceptions (Task 3)

| Path | Behaviour |
|---|---|
| `Popen()` fails | `POPEN_FAILED`, CID cleaned, `cleanup_fn` called, unscoreable |
| no container ID | `CONTAINER_NOT_CREATED`, CID cleaned, `cleanup_fn` called |
| cleanup `docker rm` fails | `DOCKER_RM_FAILED`, `cleaned=False`, `ok=False` |
| normal / timeout / overflow | `docker_cleanup` on every return branch |

`cleanup_fn` is invoked on **every** exit path including the no-cid early
return (previously skipped). Cleanup failure never silently degrades to a
scoreable success.
