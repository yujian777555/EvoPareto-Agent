# Planner Handoff — Stage 3.0-P1-R2A

**FINAL_DECISION: READY_FOR_LEVEL3_MICRO_PILOT_APPROVAL**
**REAL_LLM_CALLS: 0 · REAL_API_COST: $0**

## What was corrected

1. **Statistics (Task A)** — denominators fixed. Planner's 140/36/99/38 is exactly
   SEARCH_MAIN+SEARCH_ABLATION; R2A ALL (144/39/100/41) adds TEST_ONLY.
   succeed=38 vs upgrades=36 = 2 float-epsilon records, itemized in
   SUCCEED_FLAG_DISCREPANCY.md. Grouping, per-benchmark rates, and run-unit
   aggregates are in `corrected_statistics.json`.
2. **Inheritance (Task B)** — father/child confusion fixed. Success children are
   reselected ~7× more often than fail children (0.763 vs
   0.098); matched by creation-round quartile.
   **BEHAVIORAL_INHERITANCE_NOT_ESTABLISHED** → verdict
   **INHERITANCE_PARTIALLY_SUPPORTED**.
3. **Duplicates (Task C)** — exact vs normalized-text groups separated;
   same-parent = 28, cross-parent = 1.
   Cross-parent repeats are **by-design** of local `check_modification`, not proven bug.
   Diversity now layered (raw SHA-256 / AST / operator composition). Behavioral
   diversity = NOT_AVAILABLE.
4. **Lineage (Task D)** — GSM8K effective parents (bits, excl. initial) ≈ 3.239418554951364
   (entropy 1.6957348862067052 bits). Concentration real;
   **PREMATURE_CONVERGENCE_CAUSALLY_ESTABLISHED = False**.
   Selection probabilities = SELECTION_PROBABILITY_NOT_RECONSTRUCTABLE.
   Counterfactual rewards of untried parent–mutation pairs remain NOT_OBSERVABLE.
5. **Archive safety (Task E)** — 8 malicious-tar negative tests all REJECTED;
   official SHA-256 unchanged.
6. **Provider Gateway (Task F)** — single choke point proven (`AsyncLLM`);
   budget ledger fields complete; concurrent cap, restart persistence, unknown-price
   fail-closed all pass. Verdict **BUDGET_GATE_PASS**.
7. **Sandbox (Task G)** — real Docker negative tests (network, credentials, fs,
   docker.sock, timeout, memory, pids) all PASS. Verdict **SANDBOX_GATE_PASS**.
8. **Mock reliability (Task H)** — fresh run_id `d37d06202700`, non-zero exit
   on forced failure, events verified. Verdict **MOCK_RELIABILITY_PASS**.
9. **Micro-pilot (Task I)** — protocol + budget fixed (model deepseek-flash,
   20 GSM8K tasks, 3 rounds, $5 cap, worst-case ≈ $0.84).
   **NOT executed.**

## Gates

{
  "archive": "ARCHIVE_SAFETY_PASS",
  "provider_gateway": "BUDGET_GATE_PASS",
  "sandbox": "SANDBOX_GATE_PASS",
  "mock": "MOCK_RELIABILITY_PASS"
}

| Gate | Status |
|---|---|
| GATE_A Statistical Integrity | PASS |
| GATE_B Scientific Evidence | PASS (correlational claims bounded) |
| GATE_C Mock Reliability | PASS |
| GATE_D Safety & Budget | PASS |
| GATE_E Pilot Readiness | AWAITING_AUTHORIZATION |

## What is still NOT claimed

- AFlow's evolutionary strategy is **not** declared defective because 100 mutations
  lower scores.
- Diversity-aware parent selection is **not** declared superior; untried combinations
  have no observed reward.
- Successful-structure offspring **do not** prove capability inheritance.

## Request to Planner

Authorize the **$5 GSM8K micro-pilot** under the frozen protocol in
`MICRO_PILOT_APPLICATION.md`, or return corrections. Executor will **not** run real
model calls without explicit authorization.
