# Pilot1 Final Accounting Validation

| scenario | expected | implementation |
|----------|----------|----------------|
| usage+rate | KNOWN cost → SQLite | `estimate_cost` + settle |
| missing usage | UNKNOWN_USAGE, not fake-zero | fail-closed status |
| unknown model | UNKNOWN_RATE | no silent default rate |
| 200 empty completion | business fail | settle(success=False) |
| 401/402 | no retry | raise BillingBlocked |
| double settle | reject | ticket status |
| budget exhaust | no send | pre_send_ticket |

Backend & transport share `cost_status.estimated_cost` formula
(`deepseek-flash-2026-v1`). Provider billed cost **not** claimed.

Evidence: `tests/test_pilot1_final_admission.py`,
`results/pilot1_final_offline/native_smoke.json`.
