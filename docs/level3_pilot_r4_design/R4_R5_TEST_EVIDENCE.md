# R4-R5 Test Evidence

**Generated at run time.** Counts below are from actual JUnit XML, not estimates.

## Commands

```
python -m pytest tests/baseline_first/test_r4_exec_freeze.py --junitxml=… -q --tb=line
python -m pytest tests/baseline_first/test_r4_confirmation_audit.py …
python -m pytest tests/baseline_first/test_r4_mutation_seeds.py tests/baseline_first/test_r4_parent_adapter.py …
python -m pytest tests/baseline_first/test_r4_docker_ipc_e2e.py …
python -m pytest tests/baseline_first/test_r4_stat_consistency.py …
python -m pytest   # full
```

Log: `scripts/_r4_r5_testlog.txt` (JUnit XMLs `scripts/_j_r5_*.xml` during run).

## Actual counts (R5, JUnit)

| Step | Suite | passed | failed | errors | skipped | total | RETCODE |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | budget gate `test_r4_exec_freeze.py` | 15 | 0 | 0 | 0 | 15 | 0 |
| 2 | audit fault `test_r4_confirmation_audit.py` | 16 | 0 | 0 | 0 | 16 | 0 |
| 3 | mutation + adapter | 41 | 0 | 0 | 0 | 41 | 0 |
| 4 | freeze + stat consistency | 19 | 0 | 0 | 0 | 19 | 0 |
| 5 | docker/ipc + group C async | 17 | 0 | 0 | 0 | 17 | 0 |
| 6 | historical regression set | 93 | 0 | 0 | 0 | 93 | 0 |
| 7 | **full suite** | **1062** | **0** | **0** | **2** | **1064** | **0** |


## Suites

| Suite | Focus |
|---|---|
| `test_r4_exec_freeze.py` | budget gate, structure vs budget, R=6/10 reject |
| `test_r4_confirmation_audit.py` | strict UTF-8, fail-closed, fault injection |
| `test_r4_mutation_seeds.py` | operator dispatch, NOOP slot, lineage, seeds |
| `test_r4_parent_adapter.py` | representation, selection, Group C definition |
| `test_r4_group_c_async.py` | async two-stage contract |
| `test_r4_docker_ipc_e2e.py` | SIMULATED_DOCKER_IPC |
| `test_r4_stat_consistency.py` | RQ3 protocol table / freeze fields |
| historical | hash gate, gsm8k, budget, scoring |

## Integrity checks (pre-commit)

| Check | Expected |
|---|---|
| R3 results vs baseline | 0 modified |
| R3 `EXPECTED_TASK_HASH` | unchanged |
| v1 confirmation SHA | `1771a67c…` |
| v0 execution freeze file | preserved |
| Authorization | read-only; attempts=244; spent=0.0363972 |
| Real API this round | **0** |

## Unresolved kept open

* Live-repo audit independence is **BLOCKED** by legacy non-UTF-8 `docs/PHASE2_EVOLUTION_MEMORY.md` (see statistical/contamination notes).
* Formal freeze / preregistration **not** approved.
