# Stage 1.5 Failure Taxonomy

**Data:** 18 real Stage 1 episodes + DecisionLogs (`results/stage1_feasibility/episodes/`)  
**Artifact:** `results/stage1_5/failure_classification.json` (recomputable)

---

## Progress stages (evidence-based)

| Stage | Rule | Episodes reaching |
|---|---|---:|
| Goal Identified | non-empty goal in episode | 18/18 |
| Relevant Object Discovered | object term in env feedback (task text stripped) | **4**/18 |
| Object Manipulated | `take`/`pick` of target | **2**/18 |
| Required Intermediate State | light toggled or object moved to target | **4**/18 |
| Final Goal Action Attempted | `look at obj` / winning-type action | **4**/18 |
| Native won | `success=True` | **0**/18 |

## Failure labels (multi-label, counts)

| Label | Episodes |
|---|---:|
| LOOP_STAGNATION | 17 |
| OBJECT_NOT_FOUND | 14 |
| BUDGET_EXHAUSTED | 9 |
| ENVIRONMENT_TERMINATED | 9 |
| OBJECT_FOUND_BUT_NOT_ACQUIRED | 2 |
| OBJECT_ACQUIRED_BUT_GOAL_NOT_COMPLETED | 2 |
| ACTION_PARSE_FAILURE | 5 |

### By task type
- look_at_obj_in_light (t0,t10): dominant `OBJECT_NOT_FOUND` + `LOOP_STAGNATION`
- pick_and_place_simple (t20): `OBJECT_NOT_FOUND` (clock on shelf 3 not found) + loop

### By genome
- G3 (budget 16): more `BUDGET_EXHAUSTED`, fewer steps
- G1/G2: run full 30 steps, still loop

## Concrete evidence (episode IDs)

| Episode | Evidence |
|---|---|
| `t0_G3_s11` | `take book 2 from sidetable 1`, `move book 2 to desk 1` — found+acquired, **goal not completed** (never reached desklamp toggle state) |
| `t10_G1_s11` | `use desklamp 1` (`You turn on the desklamp 1`) — intermediate achieved, still no `won` (laptop relation incomplete / wrong order) |
| `t20_G1_s11` | `open drawer 1`, loops dresser↔drawer — **OBJECT_NOT_FOUND** (clock is on shelf 3, never searched) |

## Q: first discovery → remaining steps

Only 4 episodes discovered the target. Where they did, steps remained after
discovery were few-to-moderate; the agent then **looped on local examine**
rather than executing the relation (under-light / move-to).

## Interpreted mechanism (not proven unique cause)

1. Search is shallow: often never leaves desk/sidetable area.
2. Even after finding the object, no persistent "I hold X / light is on / X is
   at target" state is maintained in the prompt (memory = last obs only).
3. Win-achieving ordering (hold object → toggle light) is not reliably executed.

Full per-episode rows with labels and evidence: `failure_classification.json`.
