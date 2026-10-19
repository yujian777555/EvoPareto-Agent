# Container State Verification (Task 1)

`_docker_container_gone()` no longer treats all non-zero exits as "gone".

`_docker_container_state()` returns:
- `gone` — explicit "No such container" / "No such object"
- `running` — `docker inspect` says `true`
- `stopped` — inspect succeeded but not running

Docker daemon unavailable, permission denied, and inspect exceptions all raise
`DockerCheckError` — they never pass as "gone".

Tests: state distinction (gone/running/stopped), daemon-unavailable raises,
inspect-timeout raises. Verified against the **specific** container ID.
