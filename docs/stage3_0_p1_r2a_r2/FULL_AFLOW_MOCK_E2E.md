# Full Official AFlow Mock E2E (Task 5)

**Gate D: PASS**

One real run of `scripts/stage3_0_p1_r2a_r2/run_full_aflow_mock.py` exercises:

```
Official AFlow Optimizer
  -> Official parent selection (select_round, traced)
  -> GatewayLLM -> PhysicalBudgetGate -> Mock HTTP Provider
  -> Structured modification (validated)
  -> Child Workflow validated (compile + Workflow class)
  -> Docker --network none + /ipc mailbox
  -> ModelIPCClient -> ModelIPCServer -> PhysicalBudgetGate -> Mock HTTP
  -> GSM8K offline gold scoring
  -> Experience update
  -> Result persistence
```

## Events from THIS run (not committed PASS strings)

{
  "run_id": "pytest-e2e-0001",
  "evidence_class": "MOCK_TEST",
  "OFFICIAL_OPTIMIZER_EXECUTED": true,
  "OFFICIAL_PARENT_SELECTION": true,
  "REAL_TASK_QUESTION_PROPAGATED": true,
  "STRUCTURED_MODIFICATION_VALIDATED": true,
  "CHILD_WORKFLOW_EXECUTED": true,
  "MODEL_IPC_USED": true,
  "PHYSICAL_BUDGET_CHARGED": true,
  "GOLD_ANSWER_SCORING_EXECUTED": true,
  "EXPERIENCE_UPDATED": true,
  "RESULTS_PERSISTED": true
}

`run_id` is unique per invocation. Failure exits non-zero and keeps the run id.

## Components replaced and why

| Component | Replacement | Reason |
|---|---|---|
| AFlow AsyncLLM | GatewayLLM | budget gate + mock HTTP |
| AFlow Evaluator | deterministic gold scorer | offline, no real API |
| Model in container | ModelIPCClient | controlled mailbox under `--network none` |

AFlow's Optimizer, `select_round`, experience update and result persistence are
the **official** code paths.
