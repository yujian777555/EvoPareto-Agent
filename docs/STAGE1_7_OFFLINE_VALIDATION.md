# Stage 1.7 Offline Validation

**Real DeepSeek API: 0.** Evidence: `results/stage1_7/*.json`.

## Gate A semantics — PASS
- `put a alarmclock in dresser` → object/receptacle/relation correct.
- `look at book under the desklamp` → book / desklamp / look_under_light.
- `light_on` not in held_objects; `memory none` → 0 history lines.
- Task type from public goal text. No oracle strings in new modules.

## Gate B planning — PASS
- Active subgoal persists; transitions on env evidence.
- Pickup failure → not held; place confirmation → placed.
- Candidates ⊆ admissible_commands; empty admissible → GROUNDING_BLOCKED.

## Gate C isolation — PASS
- `current` / `shared_repaired` prompts unchanged; `grounded_planner_v1` opt-in.
- Historical Stage 1/1.5/1.6 data untouched. 0 real API.

## Gate D genome — PASS (with explicit degeneracy warnings)
- memory/ budget real; planner_strategy honestly PROMPT_ONLY/UNIMPLEMENTED.
- Shared planner does not force actions.

## Gate E native offline

| Check | Result |
|---|---|
| Scripted winning sequences through EpisodeRunner | **3/3 won=true** (TECHNICAL CONTROL only) |
| Negative look-only | **3/3 stay false** |
| Generic observation-driven policy | **0/3 in 20 steps** → `INCONCLUSIVE_OR_FAIL` |

Generic policy now explores (navigates across bed/desk/drawers/shelves, even
picks up objects) but does not complete relations within budget. **Not claimed
as agent autonomy success.**

### Offline behavior metrics (evidence level)

| Metric | Value | Level |
|---|---|---|
| Goal parse tests | 7/7 | OFFLINE_TEST_CONFIRMED |
| Action grounding types | 9 types mapped | OFFLINE_TEST_CONFIRMED |
| Subgoal transition tests | 2/2 | OFFLINE_TEST_CONFIRMED |
| Scripted native completion | 3/3 | TECHNICAL_CONTROL |
| Generic policy native completion | 0/3 | FAIL/INCONCLUSIVE |
| LLM calls added by planner | 0 | CODE_CONFIRMED |
