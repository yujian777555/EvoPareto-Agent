# Planner Handoff — Level3-Pilot-R2.3.5

Popen failure path fixed:
- `proc is None` / `popen_failed` → structured failure, no `AttributeError`
- `cleanup_fn` exceptions recorded (`CLEANUP_FN_EXCEPTION`), never silent
- cleanup failure blocks scoring

Parent 11/12 · Child 11/12 ·
net gain 0 — unchanged.

Tests: 900 passed · 0 failed · 2 skipped. GitHub CI NOT_CONFIGURED.
NEW REAL HTTP REQUESTS: 0.
