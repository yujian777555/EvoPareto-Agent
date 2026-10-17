# Adversarial Test Report (Task E)

All offline. Zero real DeepSeek calls. Mock HTTP / Mock IPC only.

| Test | Expected | Status |
|---|---|---|
| New Run ID | quota not reset | PASS |
| Process restart | quota not reset | PASS |
| Delete working budget DB | quota NOT restored | PASS |
| Change DB path | quota NOT restored | PASS |
| Ledger corrupt | Fail-closed | PASS |
| Delete authorization record | Fail-closed | PASS |
| Duplicate physical request id | Reject | PASS |
| Duplicate settlement | Reject | PASS |
| Concurrent cost reservation | never exceeds cap | PASS |
| Outstanding reservations counted | cost inequality holds | PASS |
| Unknown billing | persistent block | PASS |
| Physical / token caps | pre-send reject | PASS |
| Unified gate covers optimizer + child | shared authorization | PASS |
| Historical Level 3 migration | exactly 2 requests / 162 in / 454 out | PASS |
| Invalid Graph/Prompt | 0 real requests reserved | PASS |
| prompt_contract kinds | correctly distinguished | PASS |
| compile vs load | load failure rejected | PASS |
| dependency error | attributed, no silent swap | PASS |

Test files:
- `tests/baseline_first/test_l3r2_budget_persistence.py` (19)
- `tests/baseline_first/test_l3r2_bundle_reliability.py` (10)
- `tests/baseline_first/test_l3r1_contract_ledger.py` (21)
