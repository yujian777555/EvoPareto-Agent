# Research Direction Comparison

| Dim | A: Failure Identifiability | B: Capability Inheritance |
|---|---|---|
| Scientific question | what to fix from trace? | does new capability actually fire? |
| Nearest prior | 2610.14662, EnactOpt | 2608.05810 VaG, LAGO |
| Unresolved mechanism | diagnose-vs-mutate policy | activation-level inheritance |
| Minimal change | identifiability gate in search | activation regression gate |
| EA centrality | medium (could be heuristic) | medium (gating ≠ EA) |
| Repro feasibility | medium | medium |
| Observable evidence | repair directedness metrics | activation/reachability metrics |
| Strong baselines | GEPA, CoCoEvolve | VaG, Ace-Skill, Cortex |
| Difficulty | high (needs real traces) | high (needs long evolution runs) |
| Collision risk | **HIGH** | **HIGH** |
| API/GPU cost | medium-high | medium-high |
| Falsification | gate doesn't help repair | activation gate doesn't help |

**EA centrality check:** neither is clearly an *evolutionary algorithm*
contribution — both risk being "add a verifier/gate" papers. Our goal is an EA
mechanism improvement; this argues for **not** forcing either direction now.

**Recommendation:** neither selected. Reproduce AFlow + observe limitations.
