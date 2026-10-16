# NSGA-III Audit

Source: `src/evolution/nsga3.py` (442 lines, implemented from Deb & Jain 2014).

| Check | Finding |
|---|---|
| Faithful to standard? | Yes in structure: Das–Dennis directions, non-dominated sort, niching select |
| Docstring mismatch | Docstring advertises "Supports >= 5 objectives" while project formal objective is **2-D** (`candidate_2obj`) |
| 2-D justification | **None given**; NSGA-II is the natural algorithm at M=2 |
| Budget accounting | HTTP/token budget is outside NSGA-III (BudgetDB) — fair |
| Evaluation noise | **No noise model**; LLM evals are stochastic at temperature>0 |
| Duplicate candidates | **No** built-in genome dedup before expensive evals |
| Test leakage | No test-in-the-loop found in reviewed paths |

**Recommendation:** either (a) add a genuine 3rd objective (e.g. robustness across
seeds / latency) so NSGA-III is the right vehicle, or (b) demote NSGA-III to
one baseline and headline NSGA-II + PEEM/PPEC. Do not claim "NSGA-III for
agents" without M>=3 evidence.
