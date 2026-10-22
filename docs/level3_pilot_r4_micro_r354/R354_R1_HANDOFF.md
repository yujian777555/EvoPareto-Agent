# R3.5.4-R1 Handoff — Mechanism Isolation Entry Fixes

**Baseline:** `5814ef7…` · Protocol `MICRO-R3.5.4-MECHANISM-ISOLATION-v1`  
**Real HTTP this round: 0** · No auth created · History unchanged

## Fixes

| Task | Change |
|---|---|
| **A validity/accuracy** | `classify_execution` / `is_valid_eval`; `correct=None` for invalid; `acc`/`paired` only over `valid_eval`; `COMPLETE` requires all pairs valid |
| **B feedback purity** | `build_feedback_records` classifies EXECUTION_ERROR / PARSE_ERROR / ANSWER_MISMATCH; only ANSWER_MISMATCH drives answer mutation |
| **C complete flag** | `experiment_complete` = arms ⊆ {B,A,O} ∧ all valid_eval ∧ stats COMPLETE ∧ cost_final ∧ no budget stop; else `incomplete_reason` |
| **D runtime preflight** | `preflight_runtime`: train/task SHA, counts, id↔index, disjoint, historical exclusion, baseline text, A/O feedback text |
| **E budget/calib** | caps **150 / $0.15**; Calibration marked **NOT_EXECUTED_IN_ENTRY** (frozen for future; not claimed complete) |

## Tests (actual)

35 passed / 0 failed (r354_r1_validity + r354_mechanism + r35_f_local + r34_hardset).

## Remaining limits

* Real run still **blocked** (needs matching authorization).  
* Mechanism claims await real A/O/B execution.  
* Not RSI / NSGA-III evidence.
