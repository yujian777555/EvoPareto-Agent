# Stage 3.0-P1-R2 Real AFlow History Analysis

## Archive audit

| Item | Value |
|---|---|
| source | `C:\Users\于舰\Downloads\results.tar.gz` |
| size | 51,011,459 bytes |
| SHA-256 | `F460F9C9218216F6FBAF553F4F215248317B7F37DD715AE146CD38199EABE5F7` |
| format | gzip + tar |
| integrity | OK (1720 members) |
| path traversal / symlinks | **none** |
| extracted | 1538 files → `external/AFlow_results/` (gitignored) |

## Recovered evidence

6 benchmarks (DROP, GSM8K, HotpotQA, HumanEval, MATH, MBPP) × run variants
(`graphs` main, `graphs_test` held-out, `GSM8K/ablation_graphs`).

**155 rounds** with `experience.json` (father/modification/before/after/succeed),
`graph.py`, `prompt.py`, `log.json`, per-sample CSVs.

| Variant | rounds | success | upgrades | downgrades | final best |
|---|---:|---:|---:|---:|---:|
| DROP/graphs | 21 | 5 | 4 | 14 | 0.779 |
| GSM8K/graphs | 25 | 5 | 5 | 17 | 0.910 |
| GSM8K/ablation_graphs | 21 | 9 | 8 | 11 | 0.900 |
| HotpotQA/graphs | 21 | 7 | 7 | 13 | 0.633 |
| HumanEval/graphs | 21 | 5 | 5 | 15 | 0.967 |
| MATH/graphs | 20 | 5 | 5 | 13 | 0.571 |
| MBPP/graphs | 20 | 2 | 2 | 16 | 0.849 |
| **Total** | **155** | **41** | **39** | **100** | — |

## Q-A: Do successful modifications get inherited/reused?

- Success rate **41/155 ≈ 26%** — most modifications are failures.
- **Upgrades 39 vs downgrades 100** — re-trying on successful lineages does
  NOT reliably transfer benefit; most children are worse than parents.
- **18 duplicate modification strings** appear despite AFlow's exact-string
  `check_modification` — dedup is **per-father-node**, not global, so the same
  edit can recur under different fathers.
- Successful fathers do attract more children (GSM8K/graphs: father round 8 →
  9 children, round 13 → 7).

**Conclusion:** inheritance is weak; exact-string dedup is too local. This
supports investigating *semantic/behavioral* credit instead of string matching
— consistent with our Stage 3.0-P0 LIMITATION 1.

## Q-B: Does parent selection collapse diversity?

- Graph-level diversity = 1.0 (all graph.py unique) — no identical reuse.
- **Lineage concentration:** GSM8K/graphs father counts `{null:1, 1:1, 2:1,
  3:3, 4:2, 8:9, 10:1, 13:7}` — two rounds father 16/25 children.
- **Best-score curve plateaus early:** GSM8K 0.80→0.91 by round 10 of 25
  (0.91 held 15 rounds).
- Mixed-score fathers do produce some upgrades (39 total), so low-score
  parents are not entirely useless.

**Conclusion:** structural diversity is nominally high but *lineage* diversity
collapses; early plateau suggests selection pressure/exploitation dominates.
Evidence is correlational (no counterfactual re-run).

## Limitations

- CSV per-sample scores not mined (filenames encode scores).
- log.json traces not yet parsed for invalid/duplicate rate.
- No causal identification — observational only.
