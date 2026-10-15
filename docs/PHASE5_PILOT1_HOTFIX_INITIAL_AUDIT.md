# Pilot1 Hotfix — Initial Audit

**HEAD `d9fb3d4`** = origin/main · 0 real API

## Defects

| id | location | issue |
|----|----------|-------|
| A | `http_client._send` | `actual_cost=0.0` always; rate never applied |
| B | `_send` | `settle(success=True)` on any HTTP 200, even empty completion / 4xx in body path |
| C | no CLI pilot entry | live_launcher alone ≠ runnable experiment |
