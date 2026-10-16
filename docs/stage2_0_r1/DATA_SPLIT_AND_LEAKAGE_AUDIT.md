# Data Split & Leakage Audit

Evidence: `results/stage2_0_r1/split_audit.json`.

- Unique task IDs: **PASS** (30 tasks, 30 unique `fault~seed~index`).
- Train/Dev/Test disjoint: **PASS**.
- Template-grouped split: no template crosses splits.
- Policy sees `policy_task_id()` (sha256 opaque) + symptoms/diagnosis only.
- Ground-truth `fault_type` never enters `Evidence`.

Tests: `tests/fceol_r1/test_validity.py::test_task_ids_globally_unique`,
`test_split_isolation`, `test_policy_evidence_has_no_fault_type`.
