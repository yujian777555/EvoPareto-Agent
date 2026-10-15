# Phase5-R3-R4-R2 — Success Provenance

## Historical H=30 success (old horizon JSON)

**`HISTORICAL_SUCCESS_UNREPLAYABLE`** — no action sequence saved. Not upgraded.

## New D2 evidence (valid_train, H=30, deepseek-flash)

| ep | game | success | steps | tokens in/out | cost | termination |
|----|------|---------|-------|---------------|------|-------------|
| 0 | look_at_obj … trial_T20190908_230650 | **True** | **3** | 932 / 19 | $0.000097 | won |
| 1 | look_at_obj … trial_T20190907_232227 | False | 30 | 11307 / 205 | $0.00117 | env_done |

Full step records: `observation_before/after`, `admissible_commands`, `action`,
`won`, `score`, `llm_call_count` in
`results/native_alfworld/r4r2_pilot/d2_h30_valid_train.json`.

## Replay

```text
replay_won=True, replay_steps=3, recorded_success=True, match_won=True
```

(`scripts/replay_native_trace.py` on `success_replay/episode0.json`)

## Success rule

`success = True` **only** if batch `infos["won"]` is True after `env.step`.
No keyword / capability / model-claim scoring.

## Positive control

D2 episode 0 is a **live** positive (not expert gold). Expert-only positive
control remains optional for evaluator unit checks; live won already recorded.
