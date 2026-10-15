# Agent Behavior Diagnostic Proposal

**Scope:** minimal diagnostics for the next real experiment.  
**Not implemented as production behavior changes this round** — any mechanism
change must be decided as a *shared baseline fix* vs an *experimental variable*.  
**Real API calls: 0.**

---

## C1. DecisionLog schema (next real run)

Pilot 1 stored only: `step, observation_before/after, admissible_commands,
action, score, won, done, llm_call_count`. The fields below were
**NOT_OBSERVABLE_FROM_PILOT1** and must be captured going forward.

| Field | Obtainable? | Source |
|---|---|---|
| step | yes | EpisodeRunner |
| goal | yes | EpisodeRunner.extract_goal |
| observation | yes | env |
| admissible_commands | yes | env |
| **raw_llm_response** | add logging | `InteractiveAgent` already builds `DecisionLog.raw_response` but never persists it to the episode dict |
| **parsed_action** | add | `DecisionLog.chosen_action` |
| **parse_ok** | add | `DecisionLog.parse_ok` |
| **parse_failure_reason** | add | `DecisionLog.parse_failure_reason` |
| **used_fallback** | add | `DecisionLog.used_fallback` |
| **reflection_trigger** | add | `DecisionLog.reflected` + reason |
| **reflection_response** | add | `DecisionLog.reflection_raw` |
| selected_action | yes | trajectory.action |
| environment_feedback | yes | observation_after |
| native_won | yes | env `won` |
| tokens / cost (per step) | **partial** | episode totals exist; per-step needs usage attached in `llm()` wrapper |
| memory_context | add | `MemoryStore.as_context()` snapshot per step |

Minimal patch shape (for next implementation round — **not applied now**):
persist `agent.decision_logs` into `episode["decision_logs"]` and thread
per-call token usage into the step record.

## C2. Repeated State-Action Loop Rate (RSLR)

Definition (reproducible, offline, no API):

```
For a step sequence (s_t, a_t) with t = 1..T:

  pair_t = (canonicalize(observation_before_t), a_t)
  count(p) = number of t with pair_t == p

  RSLR = (1/T) * Σ_{p : count(p)>1} (count(p) - 1)
```

- `canonicalize` strips whitespace/newline runs (string identity after strip).
- RSLR = 0 → no repeated (state, action) pair.
- RSLR → 1−1/T as the agent repeats one pair every step.
- Pilot 1: T=29, Σ(count−1)=21 → **RSLR = 21/29 = 0.724**.

Companion metrics (same definitions in `results/pilot1_postmortem/loop_metrics.json`):

```
action_repetition_ratio      = 1 - |unique actions| / T
max_consecutive_same_action  = max run-length of identical actions
max_consecutive_same_obs     = max run-length of identical observation_after
no_new_info_action_ratio     = |{t : obs_after_t == obs_before_t}| / T
```

Use: **record and analyze only** by default. Do not feed into
`candidate_2obj` formal performance. Optional auxiliary diagnostic in
logs/tables, clearly separated from the frozen objective.

## C3. Reflection trigger on stagnation

**Current:** reflection only on parse failure.  
**Proposed (not implemented here):** optional stagnation trigger, e.g.

```
if RSLR_local >= threshold over a window of W steps
   and observation_after == observation_before for the last K steps:
       force a reflection/replan call
```

### Why not implement now

Pilot/algorithm comparisons must not see a changed agent on one arm only.
Options to freeze **before** any PEEM/PPEC claim:

1. **Shared baseline fix** — add stagnation reflection to *all* methods
   (Random / NSGA-II / NSGA-III / +PEEM / +PPEC), and re-baseline.
2. **Experimental variable** — factorially vary reflection policy as its own
   treatment; do not conflate with PEEM/PPEC.

Do **not** silently strengthen only the PEEM/PPEC arm.

### Minimal-change recommendation

| Item | Proposal | Expected effect | Risk | Required test |
|---|---|---|---|---|
| Persist DecisionLog | export raw/parse_ok/fallback into episode JSON | makes H3 testable | low (logging only) | schema test; size bound |
| RSLR metric | compute offline from trajectory | quantifies looping | none (read-only) | golden vector test |
| Action-history in memory | append `action+obs_delta` to MemoryStore | may reduce repeats (H1) | changes prompt for **all** arms | loop-rate A/B offline + small live |
| Stagnation reflection | trigger on RSLR window | may break loops | must be shared or factorial | unit trigger tests; budget accounting |
| Parser strictness | require exact first-line match; log fallback | separates LLM vs parser errors | may increase fallback rate | parser unit tests |
| tool_policy / planner re-phenotype | wire into actual ALFWorld policy | restores 2 genes as real | large change — post-paper or separate study | phenotype matrix update |

**Recommended next implementation (still gated by Planner):** DecisionLog
export + RSLR metric + parser logging. Behavior changes only after the
feasibility gates (see LIVE_FEASIBILITY_PREREGISTRATION.md) say whether the
agent can solve any frozen task at all.
