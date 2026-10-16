# Stage 3.0-P1-R1 Summary

## Evidence recovery (Task A)

AFlow repo full history checked (`git log --all` on `workspace/`, `*results.json`).
**`results.json` / `log.json` / `processed_experience.json` were empty in EVERY
commit** — the official repo never shipped real search traces. Google Drive
dataset link recorded (not downloaded). `REAL_TRACE_EVIDENCE_INSUFFICIENT`.

## End-to-end mock validation (Tasks B–D)

`scripts/baseline_first/aflow_e2e_mock.py` ran the **official Optimizer
search loop** with MockLLM + MockEvaluator:

- `official_search_loop: PASS`, 3 rounds, 3 experience.json, results.json written
- parent selection shifted with scores (round1 → round2 once 0.62 appeared)
- findings during wiring: graph/prompt payloads must be **valid Python**;
  `load_graph` converts path→module (`workspace.GSM8K...`)

## Search mechanism audit (quantified)

| Finding | Value |
|---|---|
| parent-selection freq (2000 draws, scores 0.9/0.6/0.3) | **0.778 / 0.119 / 0.104** |
| theoretical mixed probs (α=0.2, λ=0.3) | 0.798 / 0.102 / 0.100 |
| success mod blacklisted | YES |
| failure mod blacklisted | YES |
| dedup key | exact modification string only |

**Interpretation:** strong score-bias in parent selection; experience is a
string blacklist (successes banned too). Performance impact on real tasks
**NOT_ESTABLISHED** — Level-3 pilot required.

## Gates

| Gate | Result |
|---|---|
| Evidence recovery | inventory PASS / traces INSUFFICIENT |
| Mechanism audit | PASS (quantified) |
| E2E mock | PASS |
| Empirical performance | NOT_ESTABLISHED |

**FINAL_DECISION: BASELINE_READY_GAP_UNCONFIRMED** — Level-3 real pilot is the
next step (needs Planner authorization).
