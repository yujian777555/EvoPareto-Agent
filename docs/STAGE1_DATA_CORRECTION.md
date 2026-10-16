# Stage 1 Data Correction

**Scope:** fix Pilot 1 offline analysis errors. 0 real API calls.  
**Raw episode:** `results/pilot1_live_run/pilot1_episode.json` — **unmodified (read-only)**.

---

## A1. Object-discovery misidentification — FIXED

### Bug
`scripts/analyze_pilot1_postmortem.py` scanned the whole observation blob
(including the task-description line `Your task is to: look at book under the
desklamp.`) with keyword regexes for `book` / `desklamp`. That marked:

```json
"book_location_status": "seen_in_observation",
"book_discovered": true
```

Goal wording is **not** environment evidence that the object was seen.

### Fix
New rule in `goal_progress_flags` + `strip_task_description`:

| Layer | Meaning | Counts as discovery? |
|---|---|---|
| Task Description | `Your task is to: ...` line | **No** |
| Environment Observation | env feedback text after stripping task-description lines | only this |
| Object Discovery | object term in pure env feedback | yes |
| Object Location | concrete location evidence in pure env feedback | required for a location claim |

After re-running `python scripts/analyze_pilot1_postmortem.py`:

```json
"task_description_present_in_obs": true,
"book_discovered_in_env_feedback": false,
"desklamp_discovered_in_env_feedback": false,
"book_location_status": "UNKNOWN_FROM_TRAJECTORY",
"desklamp_location_status": "UNKNOWN_FROM_TRAJECTORY",
"book_location_known_from_trajectory": false
```

Tests (`tests/test_pilot1_postmortem.py::test_task_description_not_counted_as_object_discovery`)
fail if goal text is again counted as discovery.

## A2. Loop statistics — UNIFIED

Inconsistencies observed earlier:

| Metric | old Markdown | old JSON | recomputed truth |
|---|---:|---:|---:|
| repeated (state, action) pair **types** | 8 | 6 | **6** |
| obs-change-after-action ratio | 0.643 | 0.714 | **0.714 = 20/28** |

### Definitions now (single source of truth in `DEFS`)

- **state** := `observation_before[t]`, stripped.
- **pair types** = number of distinct (state, action) pairs with count ≥ 2 → **6**.
- **loop occurrences (extra)** = Σ (count−1) over those pairs → **21**.
- **obs-change-after-action ratio** = (# of t∈[1..T−1] with
  `observation_after[t] != observation_after[t−1]`) / (T−1) → **20/28 = 0.714**.

Markdown `PILOT1_BEHAVIORAL_POSTMORTEM.md` now matches the JSON artifacts and
the recomputation. Tests recompute from the raw trajectory and assert equality
with the written JSON (`test_loop_metrics_recomputed_not_hardcoded`,
`test_written_artifacts_consistent_across_files`) — no hardcoded fake pass.

### Commands executed

```bash
python scripts/analyze_pilot1_postmortem.py
python -m pytest tests/test_pilot1_postmortem.py -q   # 6 passed
```
