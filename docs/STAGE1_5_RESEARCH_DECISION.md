# Stage 1.5 Research Decision

## Environment status

**`ENVIRONMENT_VALIDATED`**

All three frozen tasks achieve native `won=true` under expert-intent
deterministic control (7–18 steps). Negative controls correctly stay false.
Stage 1's 0/18 is **not** an environment/evaluator defect.

## Agent status

**`AGENT_SOLVABILITY_NOT_ESTABLISHED`**

18/18 failed. Progress histogram: goal 18 → discovered 4 → acquired 2 →
intermediate 4 → won 0. Dominant labels: LOOP_STAGNATION (17), OBJECT_NOT_FOUND
(14).

## Repair status

**Shared repair package (recorder + stagnation + goal-state) has offline
evidence only** — ready for A/B review, not yet validated on real LLM.

## Final next action

```
READY_FOR_SHARED_BASELINE_AB_REVIEW
```

→ **Request Planner approval** for the 24-episode real A/B
(current vs shared_repaired runtime, G1, tasks 0/10/20, caps 800 HTTP / $0.10).

**Not** authorized automatically: no API calls this round; no five-arm
evolution; no PEEM/PPEC claims.

## Ten-question summary

| Q | Finding | Confidence |
|---|---|---|
| Q1 solvable? | yes, 3/3 positive controls PASS | high |
| Q2 if fail why? | n/a — all passed; conversion gaps documented | high |
| Q3 failure stages | 4/18 discover, 2/18 acquire, 0/18 win | high |
| Q4 object contact | t0_G3_s11 book; t10_* lamp toggle | high |
| Q5 parser counts | first=10, reflect=4, recovered=4, final=6, fallback=6 | high |
| Q6 seed real? | **SEED_NOT_EFFECTIVE_FOR_LIVE_POLICY** | high |
| Q7 main defect | no persistent state → loops; shallow search | medium-high |
| Q8 repair choice | M1+M2+M3 diagnostic package (not M4) | medium |
| Q9 genome-safe? | yes — shared infra, memory_strategy keeps window control | high |
| Q10 ready for A/B? | **yes, request budget** (not auto-run) | medium |

## Bottom line

Environment works. The LLM agent cannot yet chain expert-length plans. A
minimal shared memory/stagnation/goal-state package is designed and tested
offline; it should now face a controlled real A/B before any evolutionary
study.
