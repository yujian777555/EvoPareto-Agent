# Novelty / Collision Audit (2026-10-16)

Search: arXiv API (failure+agent+evolution+mutation; agent harness+evolution).
19+ verified 2026 entries. Websearch plugin unavailable — arXiv API used
directly; IEEE/ACM DL not exhaustively covered.

## Closest works (mechanism-level)

| Work | ID | What it does | vs FCEOL | Collision |
|---|---|---|---|---|
| CoCoEvolve / Meta-Reflective Evolution | 2610.12794 | LLM mutator uses failures + full history to propose harness edits | failure→mutation, but LLM-proposed not learned operator policy | HIGH |
| Socratic-SWE | 2606.07412 | distill failure traces into skills guiding repair tasks | failure patterns→repair, not operator credit | MEDIUM-HIGH |
| Trace2Skill | 2605.21810 | mine failure modes → skills → mutator/selector | trace mining + oracle loop; no condition policy over operators | MEDIUM-HIGH |
| Mendel Gödel Machine | 2608.07645 | comparative trajectory-based self-modification | uses multi-trajectory evidence; no failure-conditioned AOS | MEDIUM |
| HERA | 2610.06563 | failures drive harness co-evolution | failure-guided, but environment co-evolution | MEDIUM |
| EvoUndo | 2608.28363 | diagnose/verify mutations recoverability | verification of mutations, not selection policy | MEDIUM |
| EvoAlloc | 2610.12086 | learn resource allocation from search experience | experience-based allocation ≈ cousin of operator learning | MEDIUM |
| Cortex | 2610.14216 | measurement-gated harness rule evolution | A/B testing rules, not failure-conditioned operators | LOW-MED |
| Classic AOS (Fialho/Li) | classic | credit/bandit operator selection | FCEOL = AOS conditioned on failure context | HIGH (family) |
| Harmony Harness / MOAE | 2610.15150 / 2609.05992 | multi-objective agent evolution | different mechanism (Pareto search) | LOW-MED for FCEOL |

## Distinguish

- Failure **Diagnosis** / **Repair** (Socratic-SWE, Trace2Skill, CoCoEvolve) ≠
  failure-**conditioned operator learning** (FCEOL).
- Intervention-**based credit** (our Δ from paired eval) ≠ trusting LLM diagnosis.

## Verdict

**NOVELTY_WEAK** — the specific combination (failure-evidence conditioning +
paired intervention credit over structural operators, with shuffled-label
control) is not directly published in the 2026 agent-evolution set, but it is
adjacent to contextual-bandit AOS and to failure-guided mutation proposals.
Incremental, not foundational. A paper would need strong held-out transfer
evidence and a clear delta vs CoCoEvolve/Socratic-SWE-style baselines.
