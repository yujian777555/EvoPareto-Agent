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

## Evidence preserved

- Original R3 task set, paired results, cost ledger, and frozen result records
  were not edited by this hardening patch.
- R3 remains an exploratory workflow comparison on 35 synthetic/unmatched
  GSM8K-style questions: parent 29/35, child 31/35; McNemar one-sided p=0.25
  and two-sided p=0.50, neither significant.
- Provenance remains 0/35 official question-plus-gold matches.
- No real API calls or model experiments are part of this patch.
- No claim is made that recursive self-improvement, NSGA-III advantage, or
  preregistration temporal order has been demonstrated.

## Test/CI reporting rule

The focused workflow is configured to run the new offline regression tests and
existing protocol tests. This document does not pre-assert a pass result; record
the actual workflow result for the final commit during Planner review.
