# Phase5-R3-R5-R1 — PPEC 2D Audit

`Preference2D` + `Preference2DController` in `src/evolution/preference_2d.py`.

| preference | weights (success, cost) |
|------------|-------------------------|
| success_first | 0.8, 0.2 |
| cost_first | 0.25, 0.75 |
| balanced | 0.5, 0.5 |

Cost direction: satisfaction uses `1 - cost`. Reference directions adapted in
2D space. `strength=0` restores uniform directions.

**Verified:** success_first picks high-perf/high-cost; cost_first picks
low-cost; dim mismatch raises; 5-obj PPEC path unchanged for legacy tests.

No 5D padding of 2D vectors.
