# Phase5-R3-R1 — Initial Code Audit

**HEAD:** `941202a` (= `origin/main`) · **Tests:** all green · **Working tree:** clean

## Call chain (evaluation)

```text
AgentGenome
  → AgentBuilder.build → Agent
  → ALFWorldRealAdapter/WebShopRealAdapter.run
      → backend.generate (LLM text)
      → _score_completion (keywords + genome capability prior)   ← PROXY
  → ObjectiveEvaluator → NSGA-III / PEEM / PPEC
```

---

## Issues confirmed in source

### I1 — Held-out leakage (P0) · `experiments/real_eval_protocol.py`

**Evidence:** `independent_test_eval` isolates only `EvaluationCache` / seed.
Adapters build tasks from **5 fixed templates** (`alfworld_real._TASK_TEMPLATES`,
`webshop_real._SHOP_TEMPLATES`). Different `task_id` suffixes are the same
content.

**Risk:** HIGH — test metrics are train-template metrics.

**Fix:** `task_fingerprint`, content-level split, leak detector, BLOCKED if no
independent content.

### I2 — Preference selection ignores PPEC (P0) · `real_eval_protocol.py:96-98`

**Evidence:** `key=lambda i: i.fitness_vector[0]` for all three preferences.

**Risk:** HIGH — cannot show PPEC preference adaptation.

**Fix:** select by `preference_satisfaction` w.r.t. the active PreferenceVector;
compare NSGA-III / +PEEM / +PEEM+PPEC; log selection difference.

### I3 — Native ALFWorld absent (P0) · `alfworld_real.py`

**Evidence:** `_score_completion` docstring: SYNTHETIC/PROXY; no env `reset/step`.
Success = `0.7*cap + 0.3*quality >= difficulty` with hand-tuned `_PLANNER_CAP` etc.

**Risk:** HIGH — no real-environment evidence.

**Fix:** attempt official ALFWorld install; else `NATIVE_ENV_BLOCKED`.

### I4 — Genome is mostly prompt/capacity prior (P0) · `agent_builder.py`

**Evidence:** genome fields written into prompt; `_mock_run` uses capability
tables; no memory store / reflection loop / tool allowlist in runtime.

**Risk:** MEDIUM-HIGH — RQ1 unproven.

**Fix:** behavioral runtime (memory read/write, reflection retry, tool policy
enforcement, budget accounting) + consistency tests; mark remaining fields
`PROMPT_ONLY` where true.

### I5 — API validation (P0) · `diagnostics.py` / `base.py`

**Evidence:** balance check uses `has_balance_fields` not `is_available`;
chat probe uses `response_len>20` not parsed `choices/message/content`;
proxy env deleted globally (`_clear_proxies_in_env`).

**Risk:** MEDIUM.

**Fix:** parse JSON properly; thread-safe budget gate; do not mutate process env.

### I6 — Baseline fairness (P1)

**Evidence needed in code:** B1 uses random mutation + NSGA-III (not NSGA-II);
B2/B3 share PEEM loop with preference flag; budget counted as pop*(gens+1)
not live API/step counts.

**Fix:** fairness audit doc + budget accounting by evaluation events.

---

## Expected deliverables

| item | status target |
|------|----------------|
| held-out protocol | content-level isolation + leak tests |
| PPEC selection | preference-utility argmax + selection-diff tests |
| Native ALFWorld | integrated or `NATIVE_ENV_BLOCKED` |
| Genome behavior | behavior tests; `PROMPT_ONLY` labels |
| API safety | parsed healthcheck + budget gate |
| Baseline audit | evidence table |
