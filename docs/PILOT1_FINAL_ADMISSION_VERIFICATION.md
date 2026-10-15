# Pilot1 Final Admission Verification

## Checklist (raw JSON)

| check | value |
|-------|-------|
| alfworld_importable | true |
| manifest_exists / valid | true |
| **manifest_game_match** | **true** |
| native_reset_pass | true |
| native_step_pass | true |
| episode_runner_pass | true |
| fitness_2d_pass | true |
| result_writable | true |
| native_dry_run_status | **PASS** |

Canonical IDs equal (trial dir vs game.tw-pddl normalized).  
`manifest_sha256=27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7`

## Billing safety

Unknown cost → persistent SQLite block; restart keeps block; no further acquire.

## E2E reconcile

Shared `estimate_cost` (deepseek-flash-2026-v1); ticket settle path; covered by
`tests/test_pilot1_microfix.py` + `test_pilot1_final_admission.py`.

## Real API calls this phase

**0**

## Status

**`ACCEPTED_PILOT1_ADMISSION`**
