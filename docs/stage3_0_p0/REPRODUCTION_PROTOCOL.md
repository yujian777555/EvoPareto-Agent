# Reproduction Protocol (proposal — NOT executed)

## Phase R1: Baseline reproduction

- Clone AFlow at a pinned commit; record license.
- Mock-model smoke: import + one workflow search loop (no paid API).
- Then (needs approval) real-model run on 2 AFlow benchmarks.
- Success criterion: non-zero baseline task success; search improves over
  random initialization.

## Phase R2: Limitation evidence

- Replay saved trajectories (or new ones) to measure:
  - failure-directedness (2610.14662 style): does a modification fix the
    targeted failure vs the parent's other failures?
  - capability activation rates of added nodes.
- Deliver `REAL_TRACE_EVIDENCE` before any new mechanism.

## Phase R3: Minimal improvement + fair comparison

- Official AFlow vs simple heuristic vs one strong alternative vs our minimal
  change + ablation. Same budget, same tasks.

## Cost estimate (needs Planner)

- Model: any fixed LLM. Benchmarks: 2 AFlow sets (~100 tasks).
- Expected HTTP: 2,000–5,000 · tokens: 5–20M · cost: **$5–25**
  (depends on model). Hard cap proposal: $30.
- Stop: budget cap · baseline reproduces paper trend OR clearly cannot.

**Sandbox:** docker isolation; never execute generated code unisolated.
**Leakage:** SWE-bench contamination risk declared.
