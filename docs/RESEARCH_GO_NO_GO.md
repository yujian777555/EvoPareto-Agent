# Research GO / NO-GO

**Evidence base:** Pilot 1 raw trajectory + source audit (0 new API calls).  
**Commit:** analysis on `3f3da79` tree.

---

## Q1. Why did the agent loop around desk 1 / shelf 1?

**Proved (code + trajectory):**
- Memory stores only the last observation preview (`short_term` → `items[-1:]`),
  with **no action/feedback/progress** fields — repetition is invisible to the agent.
- Reflection fires **only on parse failure**, never on legal-but-stagnant actions
  (29 steps → 1 reflection, which was a parse retry).
- 21 repeated (state, action) loop occurrences; 8/29 steps returned identical
  observations; action-set divergence between halves = 0.0 (no policy change).
- `look` and `examine desk 1` toggle two fixed observation templates; the desk
  never reveals a book or lamp; the agent never opens drawers or visits other
  room objects offered at step 1 (bed, safe, drawers, shelves 2–5…).

**Plausible but unproven hypotheses:** parser substring/fallback bias; LLM
prior toward "examine/look"; missing subgoal decomposition.

**NOT_OBSERVABLE_FROM_PILOT1:** raw LLM outputs, parse_ok, used_fallback —
so we cannot yet separate *model chose to repeat* from *parser forced repeats*.

**Unknown:** true location of book and desklamp (never seen in any observation).

## Q2. Is the Agent Genome really evolvable?

| Gene | Real execution effect? |
|---|---|
| memory_strategy | **Yes** (history lines: 0 / 1 / ≤3) |
| reasoning_budget | **Yes** (max steps/tokens → cost & truncation) |
| reflection_strategy | **Degenerate** (2 levels: none vs retry-on-parse-fail; 4 names identical) |
| planner_strategy | **No** on native path (prompt label / one sentence) |
| tool_policy | **No** on native path (allowlist never consulted for ALFWorld) |

**Answer:** partially. Effective behavioral dimensionality ≈ 2–3, not 5.
If `won` is 0 everywhere, evolution collapses to **cost minimization** and
`reasoning_budget` dominates. That must be treated as a design risk, not a
result.

## Q3. If every genome fails in formal experiments, what then?

- **Do not** report cheaper failures as algorithmic success.
- **Do not** relabel progress proxies as formal performance (`won` stays frozen).
- Actions, in order:
  1. Report zero-success honestly and **stop** PEEM/PPEC superiority claims.
  2. Diagnose solvability: easier valid_train subset (development only), or
     agent repairs as a **shared baseline** (all arms), then re-baseline.
  3. If phenotype space is degenerate (Gate 2 fail), fix phenotypes first.
  4. Shrink claims to "cost-aware search under failure" only if that is
     pre-registered as a separate, weaker paper claim — not as the main story.

## Q4. GO / NO-GO for full NSGA-III + PEEM + PPEC now?

### **CONDITIONAL GO** — not full GO.

| Gate | Status now | Requirement before full run |
|---|---|---|
| Engineering chain (Pilot 1) | **PASS** (`ACCEPTED_LIVE_PILOT1_ENGINEERING`) | done |
| Gate 1 solvability | **UNKNOWN** (1 failure only) | feasibility block must show ≥1 real `won` |
| Gate 2 genome signal | **UNKNOWN / weak** (phenotype audit) | matched-pair differences |
| Gate 3 Pareto signal | **UNKNOWN** | non-trivial (performance, cost) spread |
| Fair 2-D justification of NSGA-III | **open** | empirical vs NSGA-II |

**Therefore:** run the small feasibility study first (36 or 18 episodes,
budget caps in LIVE_FEASIBILITY_PREREGISTRATION.md). Full five-arm evolution
only after Gates 1–3 pass **or** after a documented design change that all
arms share.

## Q5. Next most valuable real-API experiment?

**One controlled feasibility block** (not another single pilot):

```
6 frozen valid_train tasks × 3 preregistered genomes × 2 seeds = 36 episodes
```
caps ≈ 1400 HTTP · ≈$0.25 estimated (or 18-episode shrink ≈$0.08).

**Scientific question it answers:** *Can this agent+benchmark produce any
non-zero, genome-dependent `won` signal at a known cost?*

- Gate 1 fail → stop; repair solvability before algorithm papers.
- Gate 2/3 pass → authorize the five-arm evolutionary comparison under the
  frozen protocol in EVOLUTIONARY_EXPERIMENT_DESIGN.md.

This is the cheapest experiment that can **kill or validate** the paper's
central premise; repeating a single-episode pilot cannot.

---

## Bottom line

Engineering works; behavior loops; phenotype space is thinner than the schema
suggests; solvability is unproven. **CONDITIONAL GO:** buy the feasibility
block next, not a full evolutionary campaign.
