# Hash Gate Review (R3.1-R1)

## Fixed invariant

The frozen task set is pinned to this full SHA-256:

`ddf055537d4618c86d736d4f0ed98fd4b23efec21f9e0ffe65a2c8ee022a6219`

The serialization remains unchanged from R3: JSON encoding of ordered
`(task_id, question, gold_answer)` tuples using Python's default
`json.dumps(..., sort_keys=True)` settings, then UTF-8 SHA-256.

`load_verified_taskset()` is now the first operation in `main()`. It validates
manifest structure, exactly 35 tasks, required fields, unique IDs, task order,
declared hash, and hard-coded expected hash before checking API credentials,
opening authorization state, creating a budget ledger, or constructing an HTTP
client. The manifest's own hash cannot authorize a changed task set.

## Automated coverage

`tests/baseline_first/test_r31r1_hash_gate.py` includes 14 tests covering:

- valid frozen task set;
- question, answer, or task replacement tampering;
- task and declared-hash changed together;
- duplicate IDs and reordered tasks;
- missing fields/hashes;
- entry-point fail-closed behavior before HTTP client construction;
- offline provenance counts, no-write behavior, and unverified gold answers.

The focused GitHub Actions workflow runs these tests plus the existing R3.1/R3.2
protocol tests. It makes no real API calls. Test success must be read from the
workflow run for the corresponding commit; adding tests alone is not evidence
that they passed.
