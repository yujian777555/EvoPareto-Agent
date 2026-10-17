# Sandbox Workflow E2E + Controlled Model IPC (Task 4)

**Verdict: SANDBOX_WORKFLOW_E2E = PASS · CONTROLLED_MODEL_IPC = PASS**

## The contradiction, and the resolution

`--network none` denies **all** TCP, so a Workflow cannot open a socket to any
HTTP gateway. Declaring both "no network" and "Workflow can call the gateway"
would be a lie.

Resolution: a **bind-mounted mailbox** is the only model channel.

```text
Container (--network none, --memory, --pids-limit, --cpus, no docker.sock, no host env)
   Workflow code  --ModelIPCClient-->  /ipc/out/<id>.json
Host
   ModelIPCServer drains /ipc/out  ->  GatewayLLM  ->  PhysicalBudgetGate  ->  Mock HTTP
   writes /ipc/in/<id>.json  <-  response
```

The mailbox is the authorised host-model-service proxy. It cannot reach
arbitrary host files or external URLs; it only forwards model completions.

## Isolation matrix

| Requirement | Mechanism | Result |
|---|---|---|
| no external network | `--network none` | PASS (OSError on TCP) |
| host API key inaccessible | env not passed | PASS (None) |
| docker.sock inaccessible | not mounted | PASS (False) |
| memory / pids / cpu / time | docker flags + subprocess timeout | PASS |
| model reachable under budget | /ipc mailbox -> GatewayLLM | PASS (ledger rows written) |
| no arbitrary egress via IPC | mailbox is request/response only | PASS |

## Evidence

`results/stage3_0_p1_r2a_r1/sandbox_workflow_tests.json`
(`tests/baseline_first/test_sandbox_workflow_e2e.py`, 4 tests).

Docker negative tests from the previous stage remain valid but are **not** used
as a substitute for this runtime integration — this test runs the actual
generated-Workflow path.
