# Controlled Experiment Protocol

Frozen in `results/stage2_0/preregistration.json` (written before analysis).

- **Env:** `ControlledEnv` — mock executable workflows with 5 injected fault
  types (8 instances each, difficulty ∈ {0.3,0.5,0.7,0.9}), seed 11.
- **Split:** 60% train / 20% dev / 20% held-out (seed 7); no near-duplicate
  fault instances across splits (ids include fault prefix + index).
- **Ambiguity:** each observable symptom maps to 2 candidate mechanisms —
  same symptom can arise from different faults; operators can help some tasks
  and hurt others (complexity penalty).
- **Policies:** random, global_aos, fixed_map, fceol, shuffled, oracle.
- **Primary metric:** mean paired Δ. Secondary: success_rate, negative_rate.
- **Controls:** shuffled failure labels; wrong-diagnosis handled via UNKNOWN;
  oracle isolated (not a deployable policy).
- **Leakage:** policy sees `FailureEvidence` only (`context_key`); `fault_type`
  stays in `EvalResult` for scoring.

## Anti-self-fulfilling design

Not a lookup table: optimal operator depends on fault × genome structure;
symptoms are ambiguous; complexity penalty punishes "add everything".
