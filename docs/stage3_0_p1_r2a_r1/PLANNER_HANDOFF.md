# Planner Handoff — Stage 3.0-P1-R2A-R1 (final fix)

**FINAL_DECISION: READY_FOR_LEVEL3_MICRO_PILOT_APPROVAL**

## The three proof obligations

1. **Running tests does not pollute history** — root-caused
   (`_write`/`write_evidence` targeting `results/pilot1_*`), fixed at source
   (temp defaults + autouse redirect + `_refuse_frozen` + session SHA-256 guard).
   Full pytest leaves frozen results byte-identical.
2. **Running AFlow does not bypass budget** — both Optimizer and Workflow chains
   execute real Mock-HTTP requests through `PhysicalBudgetGate` with an
   append-only `request_ledger`; hard cap, concurrency, restart and all
   fail-closed paths tested.
3. **Running generated code cannot harm the host** — Docker `--network none`,
   no secrets, no docker.sock, cpu/mem/pids/time caps; model access only via the
   authorised `/ipc` mailbox drained by the budget-gated gateway.

## Numbers

- Entropy: 2.29597512699001 bits · N_eff 4.910858068512094 · top2 0.6666666666666666 (24 valid children)
- GSM8K: search/val on **train**, final on **test** (never in selection)
- Caps: 300 HTTP · 2M/200k tokens · **$5** hard · worst-case ≈ $0.84

## Gates

{
  "PYTEST_SIDE_EFFECTS": "NONE",
  "FROZEN_RESULTS_UNCHANGED": true,
  "ENTROPY_FORMULA": "CORRECT (log2, 2**H_bits)",
  "INITIAL_PARENT_NODES_EXCLUDED": true,
  "OPTIMIZER_GATEWAY_E2E": "PASS",
  "WORKFLOW_GATEWAY_E2E": "PASS",
  "REQUEST_LEDGER_PERSISTENT": "PASS",
  "BUDGET_FAIL_CLOSED": "PASS",
  "SANDBOX_WORKFLOW_E2E": "PASS",
  "NO_UNAUTHORIZED_EGRESS": "PASS",
  "GSM8K_TRAIN_VALIDATION_TEST_SPLIT": "FROZEN",
  "REAL_LLM_CALLS": 0,
  "REAL_API_COST_USD": 0,
  "FINAL_DECISION": "READY_FOR_LEVEL3_MICRO_PILOT_APPROVAL"
}

## Request

Authorize the frozen $5 GSM8K micro-pilot. Executor will **not** send any real
DeepSeek request without explicit Planner approval.
