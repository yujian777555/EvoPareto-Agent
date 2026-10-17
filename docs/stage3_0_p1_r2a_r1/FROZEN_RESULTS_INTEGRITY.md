# Frozen Results Integrity (Task 1)

**Verdict: FROZEN_RESULTS_UNCHANGED = TRUE**

## Method

`tests/frozen_guard.py`:

- `tracked_results_files()` — `git ls-files results/`
- `snapshot()` — SHA-256 per tracked file
- `assert_frozen_unchanged(before, after)` — fails on added / removed / modified

Captured snapshot: `results/stage3_0_p1_r2a_r1/frozen_result_hashes.json`
(306 tracked files).

## Evidence

```text
python -m pytest            -> 625 passed
git status --porcelain      -> only intentional source/doc changes
git diff --name-only        -> no results/pilot1_* modifications
```

The three previously polluted files remain byte-identical to their committed
state:

- `results/pilot1_preflight/timeout_billing_block.json`
- `results/pilot1_live_admission_verified/atomic_billing_block.json`
- `results/pilot1_live_admission_verified/live_manifest_mock.json`

## Policy

Tracked experiment records under `results/` are **never** added to `.gitignore`.
If a test legitimately needs to read/write JSON experiments it must copy into
`tmp_path` first. `git checkout` is not used as a cleanup mechanism.
