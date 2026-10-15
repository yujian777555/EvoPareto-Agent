# Phase5-R3-R3 — Episode Isolation

## Problem (audit A1)

One `InteractiveAgent` shared across episodes leaked MemoryStore, BudgetMeter,
reflection counters; API usage was cumulative.

## Fix

`src/runtime/episode_runner.py` `EpisodeRunner`:

```text
reset game (episode_index rotation)
extract goal from env
make_agent() → fresh MemoryStore + BudgetMeter
usage snapshot per episode (calls / tokens / cost delta)
execute until won | env_done | budget_exhausted | stalled | max_steps
```

`make_agent()` always constructs a new InteractiveAgent.

## Tests

- `test_episode_memory_not_shared`
- `test_episode_budget_isolated`
- `test_reflection_state_isolated`

## Game rotation

`NativeALFWorldEnv.reset(episode_index=)` loads `game_files[episode_index % n]`
and stamps `extra.gamefile` into infos. Micro pilot now shows **2 distinct
game IDs** (was 1).

## Transfer mode

Cross-episode memory transfer is **not** enabled by default (explicit future work).
