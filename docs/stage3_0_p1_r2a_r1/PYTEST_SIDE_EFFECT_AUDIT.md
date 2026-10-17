# Pytest Side-Effect Audit (Task 1)

**Verdict: PYTEST_SIDE_EFFECTS = NONE**

## Root cause

Two test modules wrote evidence JSON **directly into tracked experiment
directories**:

| File | Writer | Frozen path hit |
|---|---|---|
| `tests/test_pilot1_preflight.py` | `_write()` | `results/pilot1_preflight/timeout_billing_block.json` |
| `tests/test_pilot1_final_patch.py` | `write_evidence()` | `results/pilot1_live_admission_verified/{atomic_billing_block,live_manifest_mock}.json` |

They used module-level `RESULTS = Path("results/...")` as the output target.
Read-only consumers (`test_pilot1_microfix`, `test_pilot1_postmortem`,
`test_stage3p1*`) were not involved.

## Fix (source-level, not git-checkout)

1. **Test modules default to a temp dir.** `RESULTS` in both writers is now
   `tempfile.mkdtemp(prefix="evo_test_...")`. Production experiment writers live
   in `scripts/` and take an explicit `output_dir`; real-experiment write paths
   are unchanged.
2. **Autouse fixture redirect** (`tests/conftest.py`) — any module that defines a
   write helper (`_write` / `write_evidence`) and still points `RESULTS` at a
   frozen directory is redirected into `tmp_path/pytest_evidence/` for the test
   body. Read-only modules (e.g. postmortem) are **not** redirected.
3. **`_refuse_frozen()`** raises `RuntimeError` if a write helper is invoked with
   a frozen `results/` target while `PYTEST_CURRENT_TEST` is set.
4. **Session guard** `frozen_results_guard` snapshots SHA-256 of every
   git-tracked `results/` file before the session and asserts equality after —
   it runs even when tests fail.

## Covered exit paths

| Path | Protection |
|---|---|
| TEST_SUCCESS | source redirect + hash guard |
| TEST_FAILURE | same (teardown still runs) |
| TEST_EXCEPTION | same |
| TEST_INTERRUPTED / SIGKILL | source redirect is the real barrier — writes never target `results/` |

**The design forbids writing frozen results; it does not repair them afterwards.**

## Evidence

`results/stage3_0_p1_r2a_r1/pytest_side_effect_tests.json` and
`tests/test_frozen_results_integrity.py` (8 regression tests).
