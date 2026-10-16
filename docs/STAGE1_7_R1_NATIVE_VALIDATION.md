# Stage 1.7-R1 Native Validation

Evidence: `results/stage1_7_r1/native_offline_results.json` (Docker, 0 real LLM).

| Check | Result |
|---|---|
| Scripted technical control (tasks 0/10/20) | **3/3 won=true** (wiring only) |
| Negative look-only | **3/3 stay false** |
| Generic observation-driven | **0/3 won** in 20 steps |
| Generalization probe (unseen Bowl/DeskLamp instance) | **0/1** but **found & took `bowl 1`** |

## Generic policy traces (honest)

- t0: `take book 1` (correct object) then `move book 1 to bed 1` (wrong place loop)
- t10: explored armchairs/bed, `take laptop 1` (correct)
- gen (bowl): `take bowl 1 from desk 1` (correct discovery on a new game)

**Target-first ranking works** (right object picked). Remaining failure is the
generic heuristic chaining to tool-use / correct placement — **not** planner
state corruption.

## Failure-cause judgment

| Cause | Status |
|---|---|
| Planner state errors | **fixed in R1** (transition tests) |
| Candidate selection | improved; target actions no longer buried |
| Generic heuristic capability | **dominant remaining limit** |
| Horizon | 20 steps vs expert 4–18 with known targets |

Stage 1.7 historical 0/3 result **preserved** (not overwritten).
