# Stage 1 Feasibility Results

**Execution SHA:** `6694f78865dd4a960b312f76a3732b6c7613fe2d`  
**Manifest SHA256:** `27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7`  
**Episodes:** 18 / 18 executed once each · **Successes: 0**  
**Status:** `STOP / SOLVABILITY_DIAGNOSIS` (Gate 1 FAIL)

---

## 1. Budget & ledger (complete, honest)

| Item | Value | Cap |
|---|---:|---:|
| Episodes | **18** | 18 |
| Physical HTTP | **472** | 650 |
| Input tokens | **153,539** | — |
| Output tokens | **2,641** | — |
| Estimated cost | **$0.0492309** | $0.11 |
| settled_ok / failed | 472 / 0 | — |
| open tickets | 0 | — |
| retries | **0** | — |
| billing_blocked | **false** | — |

Cost formula check (peak conservative):
`153539×0.30/1e6 + 2641×1.20/1e6 = 0.0492309` ✓ exact.

## 2. Gate results

| Gate | Result | Evidence |
|---|---|---|
| **G1 solvability** | **FAIL** (0/18 `won=true`) | `gate_decisions.json` |
| **G2 genome distinction** | **COST_DISTINGUISHABILITY_ONLY** (0 won-diff blocks; 6 cost-only blocks) | `paired_task_results.json` |
| **G3 multi-objective** | **DEGENERATE** (all performance = 0) | `pareto_signal.json` |
| **Final** | **STOP / SOLVABILITY_DIAGNOSIS** | preregistered rule |

## 3. Genome-level aggregates (6 episodes each)

| Genome | won | mean cost | mean steps | mean tokens_in | mean LLM calls | fallbacks | parse fails |
|---|---:|---:|---:|---:|---:|---:|---:|
| G1 baseline | 0 | $0.00293 | 29.3 | 9,164 | 30.0 | 0 | 0 |
| G2 memory/plan | 0 | $0.00365 | 30.0 | 11,434 | 30.0 | 3 | 3 |
| G3 lightweight | 0 | $0.00163 | 18.7 | 4,993 | 18.7 | 3 | 3 |
| **All** | **0** | $0.00274 | 26.0 | 8,530 | 26.2 | 6 | 6 |

**Cost/length differences are real** (G3 burns ~45% less cost by running shorter
episodes via budget=16). **Performance differences are zero** — every genome
failed every task. Per preregistration this is cost distinguishability only,
**not** performance improvement.

## 4. DecisionLog diagnostics (468 decisions)

| Metric | Value |
|---|---:|
| parse failure rate | 1.3% (6/468) |
| fallback rate | 1.3% (6/468) |
| reflection rate | 0.9% (4/468) |
| **raw LLM responses captured** | **yes** |

Top actions (whole batch): `examine desk 1`×161 · `go to drawer 1`×68 ·
`go to dresser 1`×67 · `look`×50 · `go to desk 1`×43.

### What DecisionLog newly reveals (was NOT_OBSERVABLE in Pilot 1)

- **Parser/fallback is not the loop cause**: 98.7% of decisions parse cleanly;
  fallbacks are rare and mostly on G2/G3. Repetition is largely **LLM-chosen**.
- **Agent partially understands goals** (evidence in raw responses + actions):
  - `t0_G3_s11`: found `book 2` on sidetable, `take book 2`, `examine book 2`,
    `move book 2 to desk 1` — goal is *look at book under the desklamp*; still
    did not complete the full relation before budget end.
  - `t10_*`: attempted `use desklamp 1` (4× across episodes) for *look at
    laptop under the desklamp*.
  - `t20_*`: raw response *“I need to find an alarmclock to put on the dresser”*,
    `open drawer 1/2` — correct subgoal, no successful pick-and-place.
- **G3 budget truncation is visible**: 17–19 steps then `budget_exhausted`.

## 5. Failure pattern (diagnosis, not a fix)

1. Multi-step ALFWorld goals (find → take → place/look under light) are not
   completed within 30 horizon / reasoning budget steps.
2. Heavy `examine desk 1` / location re-visit loops persist even without parse
   failures (see Pilot 1 postmortem memory limitation).
3. When the correct object appears, the agent sometimes manipulates it but
   does not reach the goal state (e.g. book moved to desk but not *under the
   desklamp* + `look at book` in that state).

## 6. Honest limits

- 0 successes → cannot claim PEEM/PPEC are ineffective; the pipeline may be
  fine and the policy simply too weak for these tasks at this horizon.
- Seed 11 vs 23 produced overlapping but non-identical trajectories (LLM
  sampling is not temperature=0); not treated as independent statistical
  replicates for significance claims.
- G3 changes several genes at once — no single-gene causal claims.

Raw artifacts: `results/stage1_feasibility/episodes/*.json`,
`raw_episode_summary.json`, `decision_log_summary.json`,
`genome_comparison.json`, `paired_task_results.json`, `pareto_signal.json`,
`gate_decisions.json`, `audit_report.json`, `budget.sqlite`.
