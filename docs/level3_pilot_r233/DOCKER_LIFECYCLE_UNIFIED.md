# Unified Docker Lifecycle (Task A)

All return branches (normal / timeout / stdout overflow / stderr overflow /
structured-result oversize / JSON parse failure / exception) now carry
`docker_cleanup` with `container_id`, `container_created`, `cleaned`, `error`.

- Container-not-created (CLI fails before --cidfile) is distinguished from
  cleanup-failure: `container_created=False`, `error=CONTAINER_NOT_CREATED`.
- `--rm` containers already gone are `ALREADY_REMOVED`, not a failure.
- Cleanup failure sets `cleaned=False` and the run is **not** a scorable
  success (`ok` requires `cleaned or not created`).
- CID file is always unlinked on every exit path.
