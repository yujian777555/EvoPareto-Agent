# LEVEL3-PILOT-R4 R5 — Planner Handoff

**Round:** `LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX-R5`  
**Start SHA:** `ed1623a7fae56d6293fb05a71258b5d3747af7c5`  
**End SHA:** `ed1623a…` → (push target)  
**Real API requests:** **0**

---

## Defect fixes

| Defect | Fix | Evidence |
|---|---|---|
| Budget gate ignored real caps | `compute_budget_requirements` + `verify_budget_feasibility` + `verify_exec_freeze(require_budget=True)`; structure ≠ budget | R=6/10 **REJECT** `BUDGET_REQUESTS_EXCEEDED` |
| Float margin 1849 vs 1848 | exact `Fraction` ceil | 528 / 1848 / 2904 |
| Audit `errors="replace"` | strict UTF-8; decode error → BLOCKED | `FILE_DECODE_ERROR…required_text=true` |
| Binary docker logs confused with text fail | explicit `NON_TEXT_BASENAMES` exclusion | test binary stdout still VERIFIED on clean tree |
| `M_SINGLE_EDIT` not dispatched | branch + `single_edit_pool`; no pool → FailedCandidate | `M_SINGLE_EDIT_NO_POOL` |
| Unknown operator silent | FailedCandidate `UNKNOWN_OPERATOR:…` | slot retained |
| Holm vs seed Wilcoxon conflict | F1 task Holm(5) / F2 seed {E−D,E−C}; IUT vs Holm(2) options | `R4_R5_STATISTICAL_CONSISTENCY.md` |
| E−C missing from RQ3 claim | co-primary + claim rule “both must pass” | freeze v1 `rq3_comparisons` |
| Docker/IPC NOT VERIFIED | SIMULATED_DOCKER_IPC E2E | 6 tests, daemon 29.3.1 |

## Budget gate verdict (before any HTTP)

| R | +10% requests | tokens_out worst | USD | Decision |
|---:|---:|---:|---:|---|
| 1 | 528 | 422,400 | $1.58 | REJECT requests |
| 6 | 1,848 | 1,478,400 | $5.54 | REJECT requests (USD would also fail) |
| 10 | 2,904 | 2,323,200 | $8.71 | REJECT requests (USD/token also fail) |

## Test counts (JUnit, this round)

15 + 16 + 41 + 19 + 17 + 93 targeted; **full 1062 / 0 / 2 (1064)** RETCODE 0.

## Execution layers

| Layer | Status |
|---|---|
| SIMULATED_LOCAL | READY |
| SIMULATED_DOCKER_IPC | READY |
| REAL_MODEL | BLOCKED |
| Formal experiment | NOT APPROVED |

## Integrity

R3 results 0 modified; R3 gate unchanged; v1 confirmation SHA `1771a67c…`; v0 exec freeze preserved; auth read-only 244 / $0.0363972.

## Open for Planner

1. F2-a Holm(2) vs F2-c IUT for {E−D, E−C}.  
2. Legacy `PHASE2_EVOLUTION_MEMORY.md` non-UTF-8 blocks live-repo audit independence (exclude vs re-encode — **not** done).  
3. Accept exec freeze **v1** later; **not** approved now.  
4. New request/token authorization required for any real run.

## STOP

No formal experiment, no prereg sign-off, no real API. Awaiting Planner.
