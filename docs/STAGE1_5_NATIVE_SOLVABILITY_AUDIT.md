# Stage 1.5 Native Solvability Audit

**Verdict: `ENVIRONMENT_VALIDATED`** — all three frozen tasks reach native `won=true`
via expert-INTENT deterministic control (no LLM). Negative controls stay false.

Environment: Docker `alfworld-local:tw` + volume `alfworld-data`  
Evidence: `results/stage1_5/{positive,negative}_controls.json`, `native_won_validation.json`  
**Real DeepSeek API calls: 0**

---

## Q1. Can the three frozen tasks reach native won=true?

| Task | Type | Status | Steps | Winning action sequence (abridged) |
|---:|---|---|---:|---|
| 0 | look_at_obj_in_light Book/DeskLamp | **POSITIVE_CONTROL_PASS** | 17 | `take book 2 from sidetable 1` → … → `go to sidetable 2` → **`use desklamp 1`** |
| 10 | look_at_obj_in_light Laptop/DeskLamp | **POSITIVE_CONTROL_PASS** | 18 | `take laptop 1 from bed 1` → … → **`use desklamp 1`** |
| 20 | pick_and_place_simple AlarmClock/Dresser | **POSITIVE_CONTROL_PASS** | 7 | `take alarmclock 1 from shelf 3` → `go to dresser 1` → **`move alarmclock 1 to dresser 1`** |

## Q2. If any positive control had failed, why?

All three **passed**. Mapping notes (action-format conversion is non-trivial):

| Issue | Resolution |
|---|---|
| ALFRED `GotoLocation(desklamp)` ≠ `go to desklamp` | desklamp is a **furniture-mounted object**; must `go to sidetable 2` (t0) / `go to sidetable 1` (t10) then `use desklamp 1` |
| `PutObject` verb | TextWorld ALFWorld uses **`move X to Y`**, not `put` |
| Expert shelf ≠ instance | t20 clock is on **shelf 3**; deterministic search over shelves required |
| `high_pddl` field nesting | action lives in `step["discrete_action"]["action"]` |

These are **conversion gaps**, not environment defects. After grounding,
native `won` flips false → true reliably.

## Q3–Q4. Native won wiring

| Check | Result |
|---|---|
| `won` false → true on valid sequences | **yes** (3/3 tasks) |
| `won` stays false on look-only negative | **yes** (3/3) |
| EpisodeRunner would read the same `won` field | yes (`infos["won"]`) |
| Horizon 30 enough for expert sequences | **yes** (7–18 steps used) |
| force_game_file changes behavior | no — identity locked to manifest game |
| Data/version mismatch | none observed |

## Q5. Implications

- Stage 1's 0/18 is **not** explained by a broken evaluator.
- LLM agent lacks **multi-step task organization** (see failure taxonomy).
- Expert sequences are 7–18 steps; agent had budget up to 30 — **budget is
  sufficient**, policy is the bottleneck.

## Commands

```bash
docker run --rm -v alfworld-data:/data -v <repo>/src:/src -v <repo>/scripts:/scripts \
  -v <repo>/results:/results -e ALFWORLD_DATA=/data -e PYTHONPATH=/ \
  alfworld-local:tw python /scripts/stage1_5_native_controls.py
```
