# Planner Handoff — Level3-Pilot-R3.1-R1

## What changed

1. **Hash gate hardened** — `EXPECTED_TASK_HASH` is the full frozen SHA-256;
   `verify_taskset()` enforces recomputed == declared == expected with
   field/ID/order checks first. 11 regression tests.
2. **Provenance audit reproducible** — standalone script with SHA-256 and
   record-count verification; reproduces 0/35 match finding.

## Unchanged

- R3 original results preserved (35 synthetic tasks, parent 29/35 vs child
  31/35, McNemar one-sided p=0.25 / two-sided p=0.50)
- Provenance remains **NOT verified** (0/35 official matches)
- Frozen results (398 files) untouched
- Authorization ledger untouched; 56 requests remain
- NEW REAL HTTP REQUESTS: **0**

## Not claimed

- official GSM8K generalization
- statistical significance
- recursive self-improvement
- preregistration temporal ordering (not Git-provable in single commit)
