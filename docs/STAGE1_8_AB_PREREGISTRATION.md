# Stage 1.8 A/B Preregistration

Frozen before execution (`results/stage1_8/preregistration.json`).

```
3 tasks (0,10,20) × 2 runtimes (current | grounded_planner_v1) × G1 × 1 repeat = 6
```

Order (shuffle seed 2026): t0_grounded, t0_current, t10_current, t10_grounded,
t20_grounded, t20_current.

Caps: **6 episodes · 200 HTTP · $0.04** · `deepseek-flash` · temperature 0 ·
thinking disabled · horizon 30 · manifest `27b54ac0…` · prompt
`STAGE1_8_GROUNDED_PROMPT_V1`.

Gate 1: ≥1 grounded `won` → signal. Gate 2: paired comparison. Gate 3: cost
reporting (per-success undefined if 0). Gate 4: planning behavior (auxiliary).
