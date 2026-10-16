# Stage 1 Feasibility Preregistration

**Frozen before any Stage 1 real request.**  
Artifacts: `results/stage1_feasibility/{experiment_config,experiment_matrix,preregistration}.json`  
**Approved budget: 18 episodes · 650 physical HTTP · $0.11 estimated cost (batch totals).**

---

## Design

```
3 frozen valid_train tasks  ×  3 preregistered genomes  ×  2 seeds  =  18 episodes
```

### Frozen tasks (verified from real manifest)

| task_index | type | game_id |
|---:|---|---|
| 0 | look_at_obj_in_light | `.../look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990` |
| 10 | look_at_obj_in_light | `.../look_at_obj_in_light-Laptop-None-DeskLamp-309/trial_T20190907_185713_398582` |
| 20 | pick_and_place_simple | `.../pick_and_place_simple-AlarmClock-None-Dresser-319/trial_T20190910_195319_108102` |

Manifest SHA256: `27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7`

### Frozen genomes

| id | planner | memory | reflection | tool_policy | budget |
|---|---|---|---|---|---:|
| G1 | cot | short_term | self_critique | balanced | 64 |
| G2 | plan_and_solve | episodic | none | conservative | 64 |
| G3 | direct | none | none | no_tools | 16 |

G3 changes several genes + budget at once → comparisons are between **whole
configurations**, not single-gene causal claims.

### Seeds and order

- seeds `[11, 23]` for every genome×task.
- Execution order frozen in `experiment_matrix.json` (18 unique cells,
  shuffled within each (task, seed) block by `random.Random(2026)`).
- No mid-run reordering; no automatic retry of failed cells.

### Seed caveat (honest)

Temperature is **not set** in the HTTP payload (provider default). Forced
identical game loading + non-zero sampling can still vary; conversely if the
provider is effectively deterministic, seed 11 vs 23 may duplicate. That will
be **recorded as observed**, not manufactured into "independent samples".

## Budget gates (batch totals)

```
episodes_max: 18
physical_http_cap: 650
estimated_cost_cap_usd: 0.11
```

Shared SQLite ledger for the whole batch. Reservation per attempt = peak rates
× (2000 in + 128 out). Unknown usage/rate/transport-uncertain → atomic billing
block → batch stops. Caps are **local estimates**, not provider invoices.

Pilot-1-based plan estimate (not a result): 18 × 30 HTTP ≈ 540 HTTP,
18 × $0.00267 ≈ $0.048.

## Go / No-Go (frozen — cannot be relaxed after results)

| Gate | PASS | FAIL / other |
|---|---|---|
| **G1 solvability** | ≥1 native `won=true` | all false → STOP / SOLVABILITY_DIAGNOSIS |
| **G2 genome distinction** | ≥2 paired (task, seed) blocks with differing `won` across genomes (descriptive screen) | cost-only diffs ≠ performance; else INCONCLUSIVE |
| **G3 multi-objective** | ≥1 success + ≥2 non-dominated (perf, cost) aggregates | all-zero → DEGENERATE; single unstable success → INCONCLUSIVE |

Decision rule:

```
GATE1 FAIL                        → STOP / SOLVABILITY_DIAGNOSIS
GATE1 PASS, GATE2 or 3 INCONCLUSIVE → REVIEW / NO AUTOMATIC EXPANSION
GATE1-3 support                    → REQUEST STAGE 2 APPROVAL
```

## Protocol commitments

- Performance = native `won` only. Cost = real tokens × frozen peak rates.
- Same execution layer for G1/G2/G3 (DecisionLog only; no behavior changes).
- Same tasks/seeds/cost accounting across genomes.
- All failures, timeouts, budget truncations preserved.
- No five-arm evolution in Stage 1. No PEEM/PPEC changes.
- 18 episodes only — **no automatic second batch**.
