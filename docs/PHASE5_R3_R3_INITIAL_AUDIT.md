# Phase5-R3-R3 — Initial Audit

**HEAD:** `5b0d697` (= origin/main) · Docker `alfworld-local:tw` + volume `alfworld-data` · DeepSeek `deepseek-flash` OK

## Confirmed issues in source

| id | location | finding | severity |
|----|----------|---------|----------|
| A1 | `scripts/native_llm_pilot.py` | one `InteractiveAgent` shared across episodes (memory/budget/reflection leak) | P0 |
| A2 | `InteractiveAgent.policy()` | `goal=""` always; no task goal from env | P0 |
| A3 | `select_action` budget exhausted → `"look"` (keeps stepping) | P0 |
| A4 | parse fail → `admissible[0]` silent fallback | P0 |
| A5 | `RealLLMPipeline` still proxy adapters; no native evaluator | P0 |
| A6 | `ObjectiveEvaluator._autonomy` config-name prior (circular) | P0 |
| A7 | Random Search arm = NSGA-III + random mutation | P0 |
| A8 | tool_policy `ALLOW_TOOLS` unused in native TextWorld | P1 |
| A9 | semantic/hybrid memory only string labels | P1 |

## Native env status

`AlfredTWEnv` / `TextgameBatchGymEnv` reset+step verified previously; will re-verify in Docker integration tests.

## Planned fixes

Episode factory (fresh Memory/Budget/reflection + usage delta + game_id) ·
goal extraction from reset obs · loop/budget termination · parse-fail logging ·
`native_evolution_evaluator` + RS baseline · objective audit doc · micro pilot ≤100 API calls.
