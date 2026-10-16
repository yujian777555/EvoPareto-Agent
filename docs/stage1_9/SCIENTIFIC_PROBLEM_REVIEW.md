# Scientific Problem Review (Stage 1.9)

**Search / audit date:** 2026-10-16 · Real API calls: **0**

## Candidate question

> Can Pareto evolution experience memory and preference-adaptive search
> improve the efficiency and quality of multi-objective LLM agent optimization?

## Independent assessment

| Criterion | Judgment | Evidence |
|---|---|---|
| Scientific value | **Moderate** — optimizing agent configs for performance vs cost is real | MO-CAPO/CRAFT/RSI-Router all publish on this axis (2026) |
| Already solved? | **Largely occupied** | MOAE, Harmony Harness, RoboPhD, RSI-Router cover Pareto agent evolution |
| PEEM vs PPEC roles | PEEM = operator-utility learning; PPEC = selection-side preference bias | code audit `results/stage1_9/algorithm_audit.json` |
| Joint value | Orthogonal channels **can** interact; not proven | no ablation run |
| NSGA-III fit | **Not justified for 2 objectives** | `nsga3.py` documents >=5 obj; formal objective is `candidate_2obj` |
| 3+ objectives needed? | Likely **yes** for NSGA-III to differentiate from NSGA-II | Deb & Jain 2014; 2D niching adds little |
| 2-objective enough? | Enough for a paper **only if** method is not NSGA-III-native | CRAFT/MO-CAPO show 2D accuracy-cost is a valid venue |
| Falsifiable hypotheses | **Yes** once defined (see H1–H3) | HYPOTHESES_AND_FALSIFIABILITY.md |
| Worth investing? | **Only after REFINE** | collision + phenotype issues |
| Publishable delta vs Agent Evolution papers | **Thin today** | closest five listed in literature_matrix.json |

### Honest flags

- `PEEM_INSUFFICIENTLY_NOVEL` (as currently framed vs AOS lineage)
- `PPEC_INSUFFICIENTLY_NOVEL` (static preset weights ≠ adaptive controller)
- `NSGA_III_NOT_JUSTIFIED` for 2 objectives
- `RESEARCH_HYPOTHESIS_WEAK` until measurable effect sizes are specified

The question **can be refined** into a sharper, still-open claim: *experience-
guided operator control for **expensive** multi-objective agent configuration
search under hard API budgets* — if PEEM actually shifts mutation distribution
and PPEC becomes **dynamic** (front-tracking), not a fixed weight preset.
