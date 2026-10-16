# Agent Runtime Feasibility (mini-SWE-agent)

Investigated via arXiv references (LAGO 2610.19843, SWE-Duel 2610.12569 use it).

| Item | Finding |
|---|---|
| Official repo | referenced widely; exact URL `REFERENCE_UNVERIFIED` this session |
| License | needs check at clone time |
| Deps | Python + Docker (SWE-bench evaluator) |
| OS | Docker-based → Linux containers on Windows OK |
| Model access | API keys (not used this round) |
| Trace storage | trajectories available (used in LAGO/SWE-Duel analyses) |
| Sandbox | official Docker evaluator |
| Contamination | SWE-bench leakage risk documented in literature |
| Structural modifiability | harness edits possible (EnactOpt/GEPA do this) |

**Status:** `STATIC_IMPORT_TEST` only this round — no live model evaluation.
`LIVE_REAL_MODEL_EVALUATION: NOT_EXECUTED`.
