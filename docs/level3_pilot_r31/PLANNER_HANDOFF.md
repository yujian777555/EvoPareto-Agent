# Planner Handoff — Level3-Pilot-R3.1-R1

## Changes

- Pinned the full frozen task-set SHA-256 and moved task-set validation to the
  very beginning of the experiment entry point, before API-key, authorization,
  budget-ledger, or HTTP-client setup.
- Added regression coverage for task tampering, manifest-hash tampering,
  duplicates, order changes, missing fields/hashes, and entry-point fail-closed
  behavior.
- Refactored the GSM8K provenance audit into a read-only pure audit path with
  pinned source hash/count, exact normalized question-and-gold matching,
  explicit unverified-answer handling, and count-consistency checks.
- Added focused CI for the offline regression tests and existing R3.1/R3.2
  protocol tests.

## Actual validation evidence

Code commit: `a79431868e3310441c93fa975b3f2f6a8d48ad1b`

GitHub Actions run:
https://github.com/yujian777555/EvoPareto-Agent/actions/runs/39375080988

- Workflow: `Level3 Pilot R3.1-R1 Offline Tests`
- Status: **SUCCESS**
- Test result: **41 passed / 0 failed / 0 skipped**
- The entry-point regression test patches the HTTP client and proves a
  tampered task set exits before an HTTP client can be constructed.
- The provenance test verifies the pinned source SHA-256, 1,319 records, 35 R3
  tasks, count consistency, and no writes to the source task set or audit
  artifact when using the pure audit function.

## Evidence preserved

- Original R3 task set, paired results, cost ledger, and original frozen result
  records were not edited by the hardening patch.
- R3 remains an exploratory workflow comparison on 35 synthetic/unmatched
  GSM8K-style questions: parent 29/35, child 31/35; McNemar one-sided p=0.25
  and two-sided p=0.50, neither significant.
- Provenance remains 0/35 official question-plus-gold matches.
- No real API calls or model experiments are part of this patch.
- No claim is made that recursive self-improvement, NSGA-III advantage, or
  preregistration temporal order has been demonstrated.

## Final instruction

STOP here. Await independent Planner review. Do not run another experiment or
spend API budget without a new authorization and preregistration.
