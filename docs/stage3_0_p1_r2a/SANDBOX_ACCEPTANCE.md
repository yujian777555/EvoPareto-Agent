# Sandbox Acceptance (Task G)

**Evidence class:** MOCK_TEST (real Docker negative tests)
**engine:** docker / image `python:3.10-slim`
**verdict = SANDBOX_GATE_PASS**

| Requirement | Result | Raw |
|---|---|---|
| untrusted_code_network_denied | PASS | `NET_DENIED:OSError
` |
| host_credentials_inaccessible | PASS | `SECRET=<absent>
` |
| host_filesystem_restricted | PASS | `SEEN False False ['home', 'srv', 'etc', 'var', 'opt', 'sys', 'boot', 'sbin', 'de` |
| docker_socket_inaccessible | PASS | |
| execution_timeout_enforced | PASS | |
| memory_limit_enforced | PASS | |
| process_limit_enforced | PASS | |

Real Docker negative tests. Pilot must use: docker run --network none --memory 256m --pids-limit 64 with env keys stripped and no docker.sock mount.

Local `tempfile` directories are **not** a system sandbox. Real isolation is Docker
with `--network none`, stripped environment, memory and pids limits, and no
`/var/run/docker.sock` mount. All checks above were executed as negative tests in
this stage — not merely written as policy.
