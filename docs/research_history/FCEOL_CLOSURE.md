# FCEOL Closure

**Status:** `CLOSED / NEGATIVE_RESULT_PRESERVED`  
**Decision date:** 2026-10-16 · **Decided by:** Planner

## Original hypothesis

Failure-conditioned evolutionary operator learning (FCEOL): conditioning
mutation-operator selection on agent failure evidence + paired intervention
credit would beat global AOS / random / fixed maps.

## Stage 2.0 (invalid)

Reported `fceol − global_aos = +0.159 mean Δ` on held-out. **Invalid because:**

- Task IDs collided (all `FAULT_*` prefix → 8 unique IDs for 40 records).
- `ControlledEnv` used static `fault_type → reward` lookup (self-fulfilling).
- Shuffled control used unstable `hash()` and inconsistent credit keys.
- Held-out evaluation updated the policy (leakage).
- Oracle repeated one operator and scored negative (broken ceiling).
- Invalid test assertion `or True` bypassed checks.

## Stage 2.0-R1 (valid negative)

After full repair (real interpreter, unique IDs, template splits, frozen
transfer, exact enumeration oracle, 10 seeds):

```
frozen mean_final_reward: fceol = contextual_bandit = global_aos = 0.200
fceol − contextual_bandit = 0.000
oracle ceiling = 0.384
success_rate = 0 for all policies
```

**FCEOL provides no measurable advantage over standard contextual bandit or
global AOS.** Evidence quality (true vs shuffled/unknown) has a small effect
(+0.02) but *conditioning the policy* does not.

## Mechanism overlap

FCEOL is a contextual-bandit UCB over failure-context keys — the same family
as classic Adaptive Operator Selection. The "failure-conditioned" part is an
input feature, not a new learning algorithm. `PEEM_INSUFFICIENTLY_NOVEL`
lesson repeated.

## Risks recorded

- Failure symptoms are often non-identifying (same symptom, different root
  cause) — the environment itself limited what any policy could learn.
- 3-step budget and 2/6 solvable tasks constrained success rates.
- Single synthetic environment.

## Reusable assets (kept)

- `src/research/fceol_r1/workflow_interpreter.py` (real node execution).
- `task_suite.py` (unique IDs, template splits).
- `evaluator.py` (frozen vs online protocols).
- Math-contract fix in `credit_assignment.py`.
- Negative results in `results/stage2_0_r1/` (immutable).

## Why closed

1. No advantage over standard baselines after valid testing.
2. Mechanism is AOS/contextual-bandit re-skinned.
3. Better-published 2026 work covers failure-guided agent evolution
   (EnactOpt, CoCoEvolve, "Does Failure Feedback Direct Agent
   Self-Modification?").

**No further FCEOL tuning without a new Planner-approved hypothesis.**
