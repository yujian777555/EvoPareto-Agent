# Multiseed Results

Real run: `python scripts/fceol_r1/run_multiseed_experiment.py` (10 seeds,
held-out 4–6 tasks × 3 steps, frozen transfer).

## Frozen mean_final_reward (primary)

| Policy | mean | ±95% CI | success |
|---|---:|---:|---:|
| fixed_map | 0.200 | 0 | 0 |
| contextual_bandit | 0.200 | 0 | 0 |
| **fceol** | **0.200** | 0 | 0 |
| global_aos | 0.200 | 0 | 0 |
| random | 0.190 | 0.008 | 0 |
| shuffled | 0.183 | 0.007 | 0 |
| unknown_only | 0.176 | 0 | 0 |
| wrong_diagnosis | 0.176 | 0 | 0 |
| **oracle (enum)** | **0.384** | — | (some tasks 0.6+) |

## Paired differences (fceol − X)

| X | mean diff |
|---|---:|
| contextual_bandit | **0.000** |
| global_aos | **0.000** |
| shuffled | +0.017 |
| unknown_only | +0.024 |
| random | +0.010 |

## Online adaptation (Protocol B)

fceol 0.176 · global_aos 0.176 · random 0.185 — no FCEOL advantage.

## Interpretation

- **FCEOL = contextual bandit = global AOS** under frozen transfer.
- Failure conditioning (true evidence) beats unknown-only by +0.024 and
  shuffled by +0.017 — *having* evidence helps vs destroying it, but
  **conditioning does not beat unconditioned AOS**.
- Oracle 0.384 ≫ policies 0.20: search failure, not environment flatness.
- Success rate 0: 3-step budget + 2/6 solvable tasks; no policy found the
  [M1,M2] sequence reliably.
