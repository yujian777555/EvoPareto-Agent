# Stage 1 Research Decision

**Input:** Stage 1 feasibility results (18 episodes, 0 successes).  
**Question:** does the current Agent Genome + real ALFWorld produce enough
performance variation and cost tradeoff for NSGA-III + PEEM + PPEC research?

---

## Answer

**Not yet. Stage 1 is a scientific STOP signal for the full evolutionary
campaign, not a verdict on PEEM/PPEC.**

| Question | Finding |
|---|---|
| Non-zero real success signal? | **No** (0/18) |
| Genome performance differences? | **No** (all zero) |
| Genome cost/length differences? | **Yes** (G3 ≈ 45% cheaper by early budget stop) |
| Meaningful Pareto frontier? | **No** — degenerates to cost-only ordering |
| Five-arm evolution justified now? | **No** |

## Decision

```
STAGE1_STATUS: COMPLETED
FINAL_DECISION: STOP / SOLVABILITY_DIAGNOSIS
```

Per the preregistered rule:

- Do **not** expand to 36 episodes.
- Do **not** start the five-arm NSGA-III + PEEM + PPEC comparison.
- Do **not** claim PEEM/PPEC are ineffective (there is no performance signal
  to detect their effect on).
- Do **not** report cheaper failures as algorithmic progress.

## What the evidence says about solvability

DecisionLogs (new this stage) show the agent is **not blind**:

- It surfaces and manipulates goal objects (`book 2`, `desklamp 1`,
  `alarmclock` subgoal in raw text).
- It attempts relevant actions (`use desklamp 1`, `take book 2`, `open drawer`).
- Parsing is clean (1.3% failure) — loops are mostly LLM-chosen, not parser
  artifacts.

But it does **not finish** multi-step ALFWorld goals within horizon 30 /
reasoning budget. Two concrete gaps:

1. **Search/loop efficiency** — large share of steps re-examining known
   locations (memory stores only the last observation; no action history).
2. **Goal-state completion** — even when the right object is found and moved,
   the terminal condition (`look at X under Y` / `put X on Y` + confirm) is not
   reached.

## Recommended next move (needs Planner approval — NOT executed)

**Shared execution-layer repair study** (all future arms use the same fix):

| Candidate repair | Rationale | Risk |
|---|---|---|
| Action history in memory | direct fix for loop memory gap | changes prompt for every arm |
| Slightly larger horizon / budget | see if tasks are solvable at all | raises cost; still may fail |
| Goal-state checklist prompt | help finish relations | prompt change must be shared |
| DecisionLog-guided stagnation reflection | break examine loops | must be baseline, not one arm |

Suggested minimal experiment (small, decisive):

```
Same 3 tasks × G1 × 2 seeds × 2 execution-layer variants
(current vs shared-repaired) = 12 episodes
```

Purpose: **Gate-0 solvability** — can *any* shared repair produce even one
`won=true`? If no, the benchmark/policy pairing is unsuitable for the planned
paper and the research design must change before algorithm claims.

## Hypotheses for the paper (unchanged, currently untestable)

- H_PEEM / H_PPEC remain formally stated in
  `docs/EVOLUTIONARY_EXPERIMENT_DESIGN.md`.
- Stage 1 shows they are **not yet testable**: there is no performance
  dimension for PEEM/PPEC to improve.
- Falsification conditions stay frozen; no threshold was relaxed after results.

## Reproducibility

- Execution SHA: `6694f78865dd4a960b312f76a3732b6c7613fe2d`
- Manifest SHA256: `27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7`
- Protocol: `results/stage1_feasibility/experiment_{config,matrix}.json` (frozen
  before run), `preregistration.json`
- Raw episodes + DecisionLogs: `results/stage1_feasibility/episodes/`
- Ledger: `results/stage1_feasibility/budget.sqlite` (472/472 settled, 0 retries)
