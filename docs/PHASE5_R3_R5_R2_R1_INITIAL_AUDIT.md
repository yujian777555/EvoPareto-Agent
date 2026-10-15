# R2-R1 — Initial Audit

**HEAD `9837f68`** = origin/main · tests green

## Confirmed remaining defects

| id | issue | fix |
|----|-------|-----|
| P0-A | live start not strict; tokens not in SQLite | `live_launcher` strict bootstrap; settle with tokens |
| P0-A | `_init_schema` abandoned ALL open tickets on any open | lease-safe: preserve in-flight; `recover_stale()` |
| P1-B | PPEC tests only checked directions | full env-selection test + loop selector integrity |
| P1-C | history HV still legacy 5-obj | `hv_unified` wired into `current_hypervolume` + `_record_history` |
