# Sandbox Acceptance

{
  "untrusted_code_network_denied": "Docker run with --network none (to be applied at pilot)",
  "host_credentials_inaccessible": "env keys stripped in container (to be applied)",
  "fs_restriction": "CONTAINED",
  "docker_socket_inaccessible": "verify no /var/run/docker.sock mount at pilot",
  "execution_timeout_enforced": "subprocess timeout param (implemented in extract/generate)",
  "memory_limit_enforced": "Docker --memory at pilot",
  "process_limit_enforced": "Docker --pids-limit at pilot",
  "verdict": "SANDBOX_POLICY_DEFINED"
}

**Verdict: SANDBOX_POLICY_DEFINED** — Docker `--network none`, stripped env,
`--memory`, `--pids-limit`, no docker.sock mount. Negative tests to be run in
the container at pilot start. Local tempdir is NOT a system sandbox.
