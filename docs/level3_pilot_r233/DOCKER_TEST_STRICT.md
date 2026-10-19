# Docker Test Strictness (Task B)

| Fix | Detail |
|---|---|
| missing container_id | now FAILS (was silently skipped) |
| container not created | `CONTAINER_NOT_CREATED` distinguished |
| "No such container" | treated as `ALREADY_REMOVED` (cleaned=True) |
| rm fault injection | `DOCKER_RM_FAILED` recorded, `ok=False` |
| field values | asserted per scenario, not just key presence |

Tests: normal / stdout overflow / stderr overflow / timeout / rm-failure
injection / container-not-created / no-such-container. Each verifies the
**specific** container via `docker inspect`.
