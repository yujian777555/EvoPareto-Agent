# R2-R1 — Live Pilot Final Prereg

**0 real API this phase.** Awaiting Planner approval.

## Historical cost basis (D2 valid_train H=30)

| metric | min | max |
|--------|-----|-----|
| LLM calls / ep | 3 | 31 |
| tokens in | 932 | 11,307 |
| tokens out | 19 | 205 |
| cost / ep | $0.0001 | $0.0012 |
| env steps | 3 | 30 |

## Pilot 1 (engineering only)

```bash
python -m src.runtime.live_launcher  # or experiments/pilot1_live.py
```

| knob | value |
|------|-------|
| model | deepseek-flash |
| split | valid_train |
| H | 30 |
| episodes | 2 |
| physical HTTP cap | **120** |
| cost cap | **$0.05** |
| stop | 402/401/budget/duplicate game |
| out | `results/live_pilot1/` |
| SHA | git HEAD at launch |

## Pilot 2 (feasibility)

5 arms × 8 genomes × 2 tasks ≈ 2400–3000 physical / ~$1. Needs Planner.

## Pilot 3

≥3 seeds after methods frozen.

Splits: valid_train only for dev; valid_unseen frozen (2 contaminated IDs recorded).
