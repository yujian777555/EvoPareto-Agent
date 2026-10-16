# Benchmark Comparison

Evaluated: EvalPlus (HumanEval+/MBPP+), SWE-bench Verified, BFCL, GAIA,
AgentBench/WebArena, ALFWorld. (arXiv/official docs; plugin websearch
unavailable — scoring based on known protocols + our 36-episode ALFWorld log.)

| Criterion | EvalPlus | SWE-bench V | BFCL | GAIA | AgentBench | ALFWorld |
|---|---|---|---|---|---|---|
| Base agent solvable | high | partial | high | mixed | low | **0/36 ours** |
| Objective reliability | unit tests | hidden tests | exact match | exact | tasks | native won |
| 0%/100% floor risk | low | mid | low | mid | high | **high (us)** |
| Genome can move outcome | yes | yes | yes | uncertain | yes | blocked |
| Multi-objective (perf+cost) | natural | natural | natural | ok | ok | ok in theory |
| Split discipline | easy | medium | easy | medium | medium | easy |
| Leakage | corpora | GitHub | lower | some | varies | low |
| Cheap pilot | yes | no | yes | mid | no | mid |
| Community | very high | very high | high | high | high | medium |
| Maintainability | high | medium | high | high | high | medium |

## Ranking

1. **PRIMARY — EvalPlus (HumanEval+/MBPP+):** objective pass@k via tests,
   cheap pilots, Genome can change prompt/pipeline/pass rate.
2. **PRIMARY-ALT — BFCL:** if tool-calling genes are the phenotype focus.
3. **SECONDARY — SWE-bench Verified subset:** scale-up for realism, expensive.
4. **Not primary — GAIA / AgentBench:** noisy or 0-floor risk.
5. **DROP as primary — ALFWorld:** our own evidence (Stage 1–1.8) shows
   0 native wins; continue only as stress/regression environment.

**Caveat:** none of the base success rates for *our* agent have been piloted
on EvalPlus/BFCL yet — do not claim numbers.
