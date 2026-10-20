# Planner Handoff — Level3-Pilot-R2.3.6

1. CLEANUP_FN_EXCEPTION secondary TypeError fixed — `error=None` no longer
   crashes the callback handler; failures recorded with cleaned=False.
2. Fail-closed scoring — `container_created=False` cannot score; cleanup
   failures always block scoring; `ALREADY_REMOVED` requires a real container
   ID and explicit Docker response.

Parent 11/12 · Child 11/12 ·
net gain 0 — unchanged.

Tests: 908 passed · 0 failed · 2 skipped. GitHub CI NOT_CONFIGURED.
NEW REAL HTTP REQUESTS: 0.
