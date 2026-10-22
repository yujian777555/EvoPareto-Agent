# Phase 5 Benchmark Baseline Repair — Audit Note

**Status:** CODE PATCHED · TESTS ADDED · TEST EXECUTION PENDING  
**Branch:** `planner/phase5-random-baseline-fix`  
**Scope:** offline MockLLM benchmark only; no real API calls.

## Finding

The original `experiments/run_benchmark_extension.py` declared both
`B0_random_search` and `B3_nsga3` with the same arguments:

- `use_adaptive=False`
- `experience_mode="phase2"`
- the same `MemoryEvolutionLoop` and default NSGA-III selector

Consequently, B0 was not an independent random-search baseline. The historical
B0 and B3 values are not valid evidence that NSGA-III beats random search.

## Repair

1. Implemented `run_random_search()`: sample a fresh `AgentGenome.random()`
   for every candidate evaluation; no parent selection, mutation, or
   environmental selection.
2. Random search and evolutionary arms use the same budget:
   `pop × (gens + 1) = 12 × 9 = 108` candidate evaluations per seed.
3. All optimizer arms now compute the reported final Pareto archive and HV from
   **all candidates evaluated during the run**, not only the final surviving
   population. Generation curves use the same cumulative archive basis.
4. The fixed ReAct configuration remains a static reference baseline. It is
   not an optimizer and is not budget-matched to the 108-candidate search arms;
   papers and tables must describe it accordingly.
5. Added a regression test for independent random sampling, evaluation count,
   and cumulative curve accounting.

## Commits

- `a607a022dab44d7c83258d9581a3af275faa8a8c` — random-search implementation
  and budget-matched archive metrics.
- `86064982f02d9773cd6f18e0632131a23e5eb05c` — regression test.

## Validation status

This environment could not resolve `github.com` for a local clone, so pytest
has **not** been executed here. Do not describe the patch as test-passing until
the executor runs:

```bash
python -m pytest tests/test_benchmark_extension.py -q
python -m pytest -q
python experiments/run_benchmark_extension.py
```

## Acceptance checklist

- [ ] Focused and full test suites pass.
- [ ] For B0/B2/B3/B4/B5, each seed records exactly 108 candidate evaluations.
- [ ] Each cumulative curve has 9 points and evaluation counts
      12, 24, 36, ..., 108.
- [ ] B0 is marked `uniform_random_genomes_pareto_archive`; evolutionary arms
      are marked `all_evaluated_candidates_pareto_archive`.
- [ ] Regenerated ALFWorld/WebShop tables and plots are reviewed before any
      paper claim is restored.
- [ ] The old result tables are retained as historical artifacts, not silently
      overwritten or presented as post-fix results.

## Scientific interpretation

This patch repairs baseline identity and makes archive-level search quality
comparable at a matched candidate-evaluation budget. It does **not** establish
that NSGA-III, PEEM, or PPEC is superior. Existing result tables must be
regenerated from this code and independently reviewed before use as evidence.
