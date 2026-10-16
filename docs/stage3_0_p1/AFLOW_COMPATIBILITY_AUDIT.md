# Compatibility Audit

| Category | Finding |
|---|---|
| UPSTREAM_IMPLEMENTATION | AFlow @ `3f457218…` unmodified |
| DEPENDENCY_INCOMPATIBILITY | `tree_sitter` imported by `scripts/utils/sanitize.py` but **not** in `requirements.txt`; offline pip blocked (proxy) — stubbed for import smoke only |
| ENVIRONMENT_ERROR | none after stub |
| BENCHMARK_ERROR | dataset download required for real eval — not run |
| MODEL_PROVIDER_ERROR | none (MockLLM; AsyncOpenAI never instantiated) |
| ALGORITHM_LIMITATION | experience dedup exact-string; "Absolutely prohibit" on successes |

**Upstream patches applied: none.** Any future fix must be a separate patch
file with algorithm-neutrality proof + regression test.
