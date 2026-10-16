# Stage 1.8 Live Pilot Results

**Execution SHA:** `a29a130c126712388fc86c6e1234284c2d1e0a90`  
**Episodes:** 6/6 · **current 0/3 · grounded 0/3**

## Outcomes

| Arm | n | won | mean steps | mean cost | mean tokens_in | mean loops |
|---|---:|---:|---:|---:|---:|---:|
| current | 3 | **0** | 30 | $0.00296 | 9,316 | 21.7 |
| grounded_planner_v1 | 3 | **0** | 30 | $0.00530 | 16,942 | **26.3** |
| paired | — | both_fail=3 | — | — | — | — |

`cost_per_success` = **undefined** both arms.

## Planning behavior (auxiliary)

| Episode | target discovered | acquired | tool used | placed | loops |
|---|---|---|---|---|---:|
| t0_current | yes | no | no | no | 20 |
| t0_grounded | no | no | no | no | 25 |
| t10_current | yes | no | no | no | 22 |
| t10_grounded | no | no | no | no | 27 |
| t20_current | no | no | no | no | 23 |
| t20_grounded | no | no | no | no | 27 |

Grounded **did not improve discovery** in these runs; longer prompts cost
~80% more tokens and produced **more** state–action loops.

## Budget ledger

180 HTTP / 200 · $0.02478 / $0.04 · 360 settled_ok · 0 retries · no billing block.

## Limits

3 debug tasks, 1 repeat — exploratory only. `planner_strategy` remains
PROMPT_ONLY. No PEEM/PPEC claim.
