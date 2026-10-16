# Empirical Limitation Audit

Evidence level legend: CODE_CONFIRMED (from `external/AFlow` source) ·
ARTIFACT_CONFIRMED (official workspace files) · HYPOTHESIS_ONLY.

## LIMITATION 1 — Experience usage is shallow (CODE_CONFIRMED)

- **Observed:** `format_experience` pastes "Absolutely prohibit {modification}"
  for **both** successes and failures; `check_modification` dedups exact
  strings only.
- **Source:** `scripts/optimizer_utils/experience_utils.py` lines with
  `format_experience` / `check_modification`.
- **Nearest prior:** CoCoEvolve (2610.12794) uses structured history + probes;
  2610.14662 shows failure feedback alone is weakly directed.
- **Unresolved:** semantic credit of modifications; why an edit helped/hurt.
- **EA contribution candidate:** structure-aware credit / behavioral dedup in
  parent selection — **HYPOTHESIS_ONLY** until traces exist.
- **Falsification:** if behavioral dedup ≈ exact-string dedup on real runs,
  no contribution. **Confidence: MEDIUM (code) / LOW (impact).**

## LIMITATION 2 — "MCTS" is top-k sampling (CODE_CONFIRMED / PAPER_CODE_DIVERGENCE)

- **Observed:** `select_round` = mixed softmax+uniform over top-k rounds; no
  UCT, no backpropagation, no tree edges.
- **Source:** `data_utils.py::_compute_probabilities`, `optimizer.py`.
- **Nearest prior:** classic MCTS; DAGO bandit-over-arms.
- **Unresolved:** whether true tree search or diversity pressure helps
  workflow evolution under fixed eval budget.
- **EA contribution candidate:** diversity- or novelty-aware parent selection
  vs score-only. **HYPOTHESIS_ONLY**.
- **Falsification:** score-only matches novelty-aware at equal evals.

## LIMITATION 3 — No real search traces shipped (ARTIFACT_CONFIRMED)

- **Observed:** `workspace/*/results.json`, `log.json`,
  `processed_experience.json` are all **0 bytes**. Only round_1 templates.
- **Consequence:** duplication rate, invalid-mutation rate, branch collapse,
  generalization — **NOT_MEASURABLE** from official artifacts.
- **Unresolved:** cannot yet empirically confirm G1–G5 bottlenecks.
- **Next:** Level-3 pilot must **capture full search logs**.

```text
REAL_TRACE_EVIDENCE_INSUFFICIENT
```

## Top-3 verdict

Limitations 1–2 are real code-level observations; their **performance impact**
is unproven without Level-3 runs. Limitation 3 is the binding constraint on
any novelty claim. → `HYPOTHESIS_ONLY` overall.
