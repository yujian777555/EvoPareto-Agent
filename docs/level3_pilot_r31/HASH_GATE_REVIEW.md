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

## Executed CI evidence

GitHub Actions run for code commit `a79431868e3310441c93fa975b3f2f6a8d48ad1b`:

- Result: **SUCCESS**
- Tests: **41 passed, 0 failed, 0 skipped**
- Breakdown: 14 R3.1-R1 tests + 17 R3.1 protocol tests + 10 R3.2 native-protocol tests
- No real API requests or model experiments were run.

Run: https://github.com/yujian777555/EvoPareto-Agent/actions/runs/39375080988

The workflow command is configured to retain pytest's concise pass/fail summary on
subsequent runs. A test pass proves the tested software behavior only; it does
not establish GSM8K provenance, recursive self-improvement, or statistical
significance of the original comparison.
