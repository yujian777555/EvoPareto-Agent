# Phase5-R3-R4-R2 — Four-Method Pilot Preregistration

**Status: DESIGN ONLY — not executed this phase.**

## Arms (shared native evaluator)

| arm | selection | mutation |
|-----|-----------|----------|
| Random Search | none | uniform genome sample |
| NSGA-III | NSGA-III | random |
| NSGA-III + PEEM | NSGA-III | PEEM utility |
| NSGA-III + PEEM + PPEC | PreferenceAware NSGA-III | PEEM + preference |

## Fixed budget (proposed)

- split: **valid_train only**
- H = 30
- model: `deepseek-flash`
- population / gens: **3 / 1** (micro) or **5 / 2** after Planner OK
- tasks/genome: 2
- seeds: 1 first, then 3
- **global API gate: 100 physical attempts, $1** for the first ladder
- identical task IDs for all arms (manifest, not implicit first-N)

## Metrics (record raw + transformed)

Primary: performance (won), cost (API $), tokens, steps.  
Secondary (diagnostic only until approved): HV, PSS.

## Objective status

| obj | paper table? |
|-----|--------------|
| performance | YES |
| cost | YES |
| efficiency | **NO** (quick-fail bias) |
| robustness | **NO** (redundant) |
| autonomy | **NO** (proxy) |

### Plan A vs B (for Planner)

- **A:** keep 5 axes + success-conditioned efficiency, multi-instance robustness,
  behavioral autonomy → requires re-measure & PPEC weight review.
- **B:** reduce to {performance, cost, (+optional steps)} — simpler validity,
  narrower preference demo.

**Recommendation:** execute pilot on performance+cost first (Plan B-lite) while
Plan A protocol is designed; do not report unapproved axes as method wins.
