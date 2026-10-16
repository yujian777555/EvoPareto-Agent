# PEEM Method Audit

Source: `src/evolution/pareto_experience.py`, `credit_assignment.py`, `pareto_credit.py`.

## What it actually is

Per-**mutation-type** utility table with exponential decay:

```
score_t = λ · batch_value + (1-λ) · score_{t-1},  λ = 0.35
batch_value = 0.35·improvement + 0.30·HV + 0.20·diversity + 0.15·survival
```

- **Writes:** after each offspring evaluation (online credit).
- **Reads:** to rank/select mutation operators for the next variation step.
- **Cross-generation:** yes (decay + prior smoothing).
- **Quality control:** decay + prior; **no** explicit obsolete-entry expiry.
- **Leakage:** none future-facing; uses realized child outcomes only.

## vs Archive Replay / Elite Replay

**Not** the same: PEEM stores **operator utility statistics**, not solutions.
A simple "keep best candidates" archive is a different mechanism (and is a
required control in ablations).

## vs Classic Adaptive Operator Selection (AOS)

**High overlap.** Credit-based operator selection (success reward / UCB /
probability matching) is 20 years old (Fialho; Li et al.; standard AOS
surveys). PEEM's only clear delta is the **Pareto-aware composite credit**
(improvement+HV+diversity+survival) and 2-D Pareto context.

**Verdict:** `PEEM_INSUFFICIENTLY_NOVEL` as a stand-alone method claim.
Minimal necessary improvement to claim novelty:
1. prove it changes mutation **distribution** (not just scores), and
2. show cross-problem transfer of operator utilities, and
3. beat a plain bandit-AOS baseline at equal evaluation budget.
