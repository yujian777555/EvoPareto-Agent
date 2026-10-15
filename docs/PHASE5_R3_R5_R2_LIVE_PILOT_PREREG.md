# Phase5-R3-R5-R2 — Live Pilot Prereg

**Not run this phase (0 real API).**

## Budget model (H=30 episode ≈ 30 logical LLM calls)

| Arm | genomes | episodes | logical LLM (≈30/ep) | physical HTTP (≈1.2×) |
|-----|---------|----------|----------------------|------------------------|
| Pilot 1 (wiring) | 2×5 | 10 | ~300 | ~360 |
| Pilot 2 (feasibility) | 5 arms × 8 genomes × 2 tasks | 80 | ~2400 | ~2900 |
| Pilot 3 (3 seeds) | ×3 | 240 | ~7200 | ~8600 |

**100 physical HTTP is NOT enough for five-arm evolution comparison.**
Minimum viable Pilot 2 ≈ **3000 physical requests**, ~$0.3–1.0 at flash rates.

## Views

1. equal genome evals / episodes  
2. equal HTTP / tokens / USD

## Phases

- Pilot 1: engineering (no superiority claims)
- Pilot 2: multi-task feasibility (≥20 valid_train tasks)
- Pilot 3: multi-seed (≥3) after Planner freeze

Uses `candidate_2obj`, H=30, deepseek-flash, valid_train, global SQLite gate.
