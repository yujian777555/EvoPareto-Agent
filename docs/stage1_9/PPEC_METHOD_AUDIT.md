# PPEC Method Audit

Sources: `preference_2d.py`, `preference_controller.py`, `reference_adapter.py`.

## Mechanism

1. Preference = **fixed** named preset (`success_first` / `cost_first` /
   `balanced`) or a fixed weight vector.
2. `adapt_reference_directions`: `w'_i = normalize(w_i · (ε + p_i))` —
   mass shifts toward preferred axes.
3. `preference_satisfaction` scalar ranks candidates (argmax in 2-D `select`).

## Is it a "controller"?

- **No dynamic front tracking** in the 2-D path: preferences do not update
  from observed Pareto-front shape, search stage, or external feedback.
- No closed loop beyond "given fixed p, bias directions + score".
- Therefore `PPEC` currently = **preference-articulated reference biasing**,
  which belongs to a known MOEA family (reference-point / RVEA-style
  adaptation).

## Oracle / reproducibility

- No hidden oracle signals.
- Deterministic given preference and population.

## Verdict

`PPEC_INSUFFICIENTLY_NOVEL` unless upgraded to **true adaptive control**:
e.g. infer region-of-interest from the incumbent front each generation,
or respond to budget phase (exploration → exploitation) with measurable
policy changes. Fixed 3-preset table is not a research contribution by itself.
