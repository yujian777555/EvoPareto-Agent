# MICRO-R3-OFFLINE Test & Status Report

**Real API requests:** **0** · **Real API cost:** **$0**

## Commands

```
python scripts/level3_pilot_r4/r3_offline_validation.py
python -m pytest tests/baseline_first/test_r3_offline_mutation.py -q
```

## Results (this round)

| Suite | passed | failed | notes |
|---|---:|---:|---|
| `test_r3_offline_mutation.py` | **13** | **0** | Mock LLM; socket spy blocks remote |
| `r3_offline_validation.py` | OK | 0 | writes `results/level3_pilot_r4_micro_r3_offline/r3_offline_validation.json` |

## Status ladder

| Status | Value |
|---|---|
| `EXECUTION_FIDELITY_GAP` (R2) | **CONFIRMED** |
| R3 unified executor (graph_source) | **READY (offline mock)** |
| Seeded random mutation | **READY** |
| Feedback mutation (coarse) | **READY** |
| E2 from gen-1 winner | **READY** |
| Empirical screening | **`NO_QUALIFIED_ERROR_ARCHIVE` / `BLOCKED_PENDING_API_AUTHORIZATION`** |
| Formal R4 / RSI / NSGA-III | **NOT CLAIMED** |
| Ready to request next micro real run? | **CONDITIONAL** — executor + prereg ready; needs new budget grant + optional screening |

## Unresolved

* Screening set difficulty labels need authorized model-error collection.  
* Structural graph operators beyond instruction slots not yet in default random set.  
* R2 data retained as prompt-variant evidence only.
