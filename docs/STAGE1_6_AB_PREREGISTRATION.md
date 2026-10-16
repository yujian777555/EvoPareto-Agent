# Stage 1.6 A/B Preregistration

Frozen before real requests (`results/stage1_6/preregistration.json`).  
**Design: 3 tasks × 1 Genome (G1) × 2 runtimes × 2 repeats = 12 episodes.**

## Frozen cells (exec order)

| # | task | runtime | repeat |
|---:|---:|---|---:|
| 1 | 0 | shared_repaired | 1 |
| 2 | 0 | current | 1 |
| 3 | 0 | current | 2 |
| 4 | 0 | shared_repaired | 2 |
| 5 | 10 | shared_repaired | 1 |
| 6 | 10 | current | 1 |
| 7 | 10 | shared_repaired | 2 |
| 8 | 10 | current | 2 |
| 9 | 20 | current | 1 |
| 10 | 20 | shared_repaired | 1 |
| 11 | 20 | current | 2 |
| 12 | 20 | shared_repaired | 2 |

A/B order shuffled within each (task, repeat) block (`random.Random(2026)`).

## Protocol

| Item | Value |
|---|---|
| model / rates | `deepseek-flash` · peak conservative `0.30/1.20 per 1M` |
| Genome | G1: cot / short_term / self_critique / balanced / 64 |
| horizon / split | 30 / valid_train |
| caps | 12 eps · 400 HTTP · $0.08 (batch) |
| seed label | `1000+repeat_id` — **not** a controlled LLM seed |
| Stage 1 | historical only — **current arm re-collected in this batch** |

## Gates (frozen)

| Gate | PASS | FAIL |
|---|---|---|
| G1 repaired solvability | ≥1 `won=true` in repaired | all fail |
| G2 paired improvement | ≥2 pairs (repaired win & current fail) | worse / all fail |
| G3 cost safety | median repaired ≤ 1.5 × median current | COST_SAFETY_FAIL |
| G4 loop reduction | auxiliary only | never replaces won |
