# MICRO-R3 Preregistration (offline design — PROPOSED)

**Status:** PROPOSED. **No real model calls authorized this round.**  
**R2 50-request grant is NOT auto-authorization for R3.**

## Research questions

1. On harder GSM8K-train tasks, do children beat frozen Parent?  
2. Does **feedback-driven** mutation beat **random** mutation under equal budget?  
3. Does gen-2 inherit / extend gen-1 gains?  
4. After controlling for multi-sample voting, do evolutionary candidates still win?

## Arms (operational)

| Arm | Definition |
|---|---|
| **P** | Frozen Parent graph (identity compile) |
| **R** | Seeded random mutation from P (`apply_random_mutation`) |
| **F** | Feedback-driven mutation from P (`build_feedback_child`) |
| **S** | Sampling control: P + k=2 vote (voting confound) |
| **E2** | Feedback-driven child of **gen-1 winner** (R or F by dev rule) |

All arms execute **compiled graph_source** via `execute_candidate` (unified entry).

## Data roles

* **Screening** (10): identify failure-prone items — **needs API auth** (`NO_QUALIFIED_ERROR_ARCHIVE`).  
* **Development** (5): select gen-1 winner (R vs F; max acc, tie → R first).  
* **Confirmation** (8): paired P vs winner vs E2 (and S probe).  

Indices frozen in `TASKSET_AUDIT_AND_SPLIT.md`. Gold never in solve prompts.

## Metrics

**Primary:** paired accuracy difference on confirmation; improved / regressed counts.  
**Secondary:** candidate validity rate, regression rate, gain per 100 calls, gen-to-gen delta.  
**Uncertainty:** exact McNemar two-sided; Wilson CI; report n=8 limitation.

## Failure / budget rules

* Failed candidates: retained, scored incorrect, recorded.  
* Invalid/parse/exec errors: incorrect + labeled.  
* Hard caps: **to be set by new authorization** (proposal below).  
* Stop on cap; no optional stopping; no method switch after outcomes.

## Claim boundary

N=8 confirmation. **No** statistical significance claim unless power justified. **No** RSI / NSGA-III claims. Mock ≠ real.

## Sign-off

Not approved by Executor. Requires Planner + user authorization before any real run.
