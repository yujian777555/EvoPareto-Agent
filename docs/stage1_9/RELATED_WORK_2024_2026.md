# Related Work 2024–2026

**Search date:** 2026-10-16 · Method: arXiv API (LLM+agent+evolutionary+multi-objective; Pareto; prompt NSGA; experience-guided).  
**Limitation:** platform websearch plugin unavailable; IEEE/ACM DL not exhaustively queried. Classic AOS / RVEA lines cited from knowledge, not re-fetched.

Full structured table: `results/stage1_9/literature_matrix.json` (19 entries: 16 arXiv-verified 2026 + 3 classic-adjacent).

## Closest five (deep comparison)

| ID | Title | Year | Method | Objectives | Benchmarks | vs PEEM | vs PPEC | Collision |
|---|---|---|---|---|---|---|---|---|
| arXiv:2609.05992 | MOAE | 2026 | Pareto-preserving in-context agent evolution + archive | perf, trajectory, safety | TravelPlanner, AgentDojo | archive ≈ weak PEEM control | deployment preference only | **HIGH** |
| arXiv:2610.15150 | Harmony Harness | 2026 | decomposition MOEA on compositional harnesses | task + transfer | SecRepoBench, BaxBench | no operator memory | no pref controller | **HIGH** |
| arXiv:2609.34712 | RSI-Router | 2026 | experience-guided RSI + Pareto router | perf, cost | **ALFWorld**, SciWorld, WebShop… | experience-guided evolution | Pareto selection | **VERY HIGH** |
| arXiv:2606.04661 | CRAFT | 2026 | Pareto prompt tuning, budgeted validation, NSGA-II | accuracy, token cost | 6 cls/reason sets | budget allocation | post-hoc trade-off (anti-fixed-weight) | **HIGH** |
| arXiv:2605.18869 | MO-CAPO | 2026 | MO prompt optimization vs NSGA-II | perf, inference cost | 4×3 LLMs | budget alloc | fixed cost obj | **HIGH** |

Also relevant: RoboPhD (2604.04347 / 2608.16207) budgeted agent program
evolution with price-point Pareto; EvoDrive (2606.03678) memory+Pareto archive;
FATE (2605.11882) Pareto-front policy opt; MAPLE (2609.11636) evolutionary
memory; classic AOS (PEEM family) and NSGA-III/RVEA preference adaptation
(PPEC family).

## Remaining publishable novelty

| Component | Standalone | Combined | Minimal fix |
|---|---|---|---|
| PEEM | **thin** (AOS variant) | could support *budget-aware operator control* | show distribution shift + beat bandit AOS at equal evals |
| PPEC | **thin** (static preference bias) | could support *dynamic* ROI tracking | make preference **adapt to front/budget phase** |
| PEEM+PPEC | orthogonal **interaction hypothesis only** | needs factorial ablation | run 2×2 + archive-replay control |

**Conclusion:** a paper titled "Pareto agent evolution with experience memory"
is **no longer safe**. A narrowed claim around *evaluation-cost-aware operator
control for multi-objective agent configuration search* remains open if the
mechanisms are upgraded as above and tested on EvalPlus/BFCL.
