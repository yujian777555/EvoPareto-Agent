# Planner Handoff (Stage 3.0-P1-R2)

## Done

1. **Official data recovered** — `results.tar.gz` (SHA-256 `F460F9C9…`,
   48.6MB, tar.gz clean, 1538 files) extracted to `external/AFlow_results/`
   (gitignored). 155 real rounds × 6 benchmarks.
2. **Real history analysis:** 41/155 success; **39 upgrades vs 100
   downgrades**; 18 duplicate mods despite local exact-string dedup; father
   concentration (2 rounds → 16/25 children on GSM8K); early score plateau.
3. **Q-A:** successful-mod inheritance is weak; per-father string dedup is
   insufficient (supports semantic-credit hypothesis).
4. **Q-B:** graph diversity 1.0 but lineage collapses; plateau at ~round 10.

## Research judgment

Real evidence **confirms** Stage 3.0-P0 Limitations 1–2:
- experience reuse is shallow (string blacklist, local to father),
- parent selection concentrates lineages and plateaus early.

**Impact on real performance is now measurable** (upgrades/downgrades ratio).
A minimal improvement candidate: **global semantic modification credit +
diversity-aware parent selection** vs stock AFlow — to be tested only at
Level 3.

## Remaining P1-R2 items

- E2E mock false-positive fix / run-ID isolation / exit codes: mock smoke
  scripts already isolated per-run via tmpdir; add non-zero exit in final
  validation script (small).
- Provider budget gate: reuse existing SQLite PhysicalBudgetGate (tested in
  earlier stages).
- **$5 micro-pilot application:** see below — **NOT executed**.

### Proposed micro-pilot (needs Planner)

- Model: deepseek-flash. Benchmark: GSM8K subset (20 tasks).
- 3 search rounds × sample=2; full log capture.
- Estimate: ~300 HTTP · ~2M tokens · **≤$5**, hard cap $5, fail-closed ledger.
- Purpose: measure real duplicate/invalid/upgrade rates vs this historical
  baseline.

**FINAL_DECISION: BASELINE_READY_GAP_UNCONFIRMED → READY_FOR_MICRO_PILOT_REVIEW**

`REAL_LLM_CALLS: 0`
