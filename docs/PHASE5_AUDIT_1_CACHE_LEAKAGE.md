# Phase5-Audit-1 — Cache Leakage Audit

**Priority:** P0 · **Status:** FIXED · **Algorithms:** unchanged

## Finding

`make_key()` originally hashed only `genome | benchmark | task_id | seed`.

**Missing isolation fields:** `backend`, `model`, `preference`.

Risk: a cached evaluation from MockLLM could be reused for DeepSeek (or
across preference contexts), silently corrupting multi-backend studies.

## Fix

```text
key = sha256(genome_hash | benchmark | task_id | seed | backend | model | preference)
```

- `src/runtime/cache.py` — `make_key` / `lookup` / `store` accept the new fields
- `alfworld_real.py`, `webshop_real.py`, `real_world_agent.py` — pass
  `backend.name` and `backend.model` on both lookup and store
- Legacy calls with empty fields remain stable (explicit test)

## Tests (new)

`tests/test_cache_leakage.py` (9 cases):

- key isolated by task / benchmark / seed / backend / model / preference / genome
- cross-experiment cache does **not** reuse entries
- empty-field defaults are stable

## Verification

```text
python -m pytest -q
257 passed
```

## Limitation

Preference is included in the key even though current objective evaluation is
preference-independent (preference affects *selection*, not scoring). This is
defensive isolation for future preference-conditioned evaluators.
