# Stage 1.6 Shared Runtime Implementation

**Execution SHA:** `f73299189c2b5bd92569c1b15f108e2eec9f7b38`

---

## Two explicit runtime variants

| Variant | Prompt content | Behavior |
|---|---|---|
| `current` | Stage 1 legacy (Task Goal + labels + memory History + Observation + Admissible) | **bit-identical** decisions to Stage 1 (Gate B test) |
| `shared_repaired` | current + **verified progress block** (`STAGE1_6_PROMPT_V1`) | same action parsing/fallback/reflection/budget; extra *information* only |

## What the repaired block contains

From `format_repaired_prompt_block` (`src/diagnostics/shared_repair.py`):

```
Observed Progress:
- target object (book): OBSERVED|ACQUIRED|...
- currently held: (confirmed holds only)
- light turned on: yes/not confirmed
- native task completed: no
Recent Actions and Feedback:
  step1: did=... | feedback=...
Stagnation Warning: You have repeated the same action...
```

- **No extra LLM calls** (Gate B: both variants = 2 calls for 2 decisions).
- **No forced actions** — LLM still chooses; parser/fallback unchanged.
- **No oracle fields** (traj_data/high_pddl/expert/hideen state banned; test asserts).
- Memory window still Genome-controlled: `short_term` → k=1 history line;
  progress block is *shared execution state*, distinct from memory policy.

## Evidence layering (strict)

| Fact | Source |
|---|---|
| Object discovered | env feedback text (task-description stripped) |
| Object acquired | feedback `you pick up the X` |
| Object released | feedback `you put/move the X to...` |
| Light on | feedback `you turn on the X` |
| Native won | env `won` only |

State machine: `NOT_OBSERVED / OBSERVED / ACQUIRED / RELEASED / UNKNOWN`.
Hold does not persist after a confirmed release.

## Files

- `src/diagnostics/shared_repair.py` — recorder / stagnation / goal-state / prompt block
- `src/runtime/interactive_agent.py` — `runtime_variant`, `observe()`, prompt injection
- `src/runtime/episode_runner.py` — passes variant; exports `repaired_state`
- Tests: `test_goal_state_evidence.py`, `test_runtime_integration.py`, `test_shared_repair.py`
