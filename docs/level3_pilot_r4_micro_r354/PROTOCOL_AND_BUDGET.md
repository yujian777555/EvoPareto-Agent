# MICRO-R3.5.4 Mechanism Isolation — Protocol & Budget (PROPOSED)

**Protocol ID:** `MICRO-R3.5.4-MECHANISM-ISOLATION-v1`  
**Status:** offline design complete; **real run NOT authorized** this stage.  
**Historical R3.5.3 untouched.**

## Arms

| Arm | Definition | Purpose |
|---|---|---|
| **B** | Frozen **non-empty** base strategy (separate freeze; NOT empty Parent) | baseline |
| **A** | Append same feedback text after B's strategy | feedback effect + preserve |
| **O** | Replace B's strategy with **identical** feedback text | feedback effect, no preserve |

**Primary contrast: A vs O** (strategy preservation).  
A and O share: feedback label, frozen feedback text, source FailureRecords.

## Tasksets (seed 20260606)

| Set | n | SHA |
|---|---:|---|
| Calibration | 10 | `40bf5de1f7387befeab559f5d569151d52094500c26fc5635de039630632c30e` |
| Dev | 15 | `3262fe5c71c05a54296fc42713f75747918b6e768bbd87c53e4fed3ef408131c` |
| Confirm | 30 | `e749cd1279efc5f715eea8c99455b83aefc66d89baf09788c39632c6ee4a69f2` |

Train SHA `17f347dc…`; all historical indices excluded; content-hash dedup.

## Statistics

* Task-level paired McNemar on confirm (n=30).
* Family: {A−B, O−B, A−O} with **Holm** correction.
* Seed-level: not run this stage (see multi-seed plan below).
* Failures/skips never count as correct; incomplete ≠ full stats.

## Budget estimate (full 3-arm, 1 seed)

| Block | Calls |
|---|---:|
| Calib B (optional) | 10 |
| Dev B (feedback source) | 15 |
| Confirm B+A+O (30×3) | 90 |
| Margin 10% | 12 |
| **Total** | **≈ 127** |

Worst cost ≈ 127 × $0.00081 ≈ **$0.10**; suggest cap **150 req / $0.15**.

### Multi-seed plan (R=5)

Per seed ≈ 127 → 5 × 127 = **635** req · worst ≈ **$0.51** · suggest cap **700 / $0.60**.  
Seed-level analysis then possible (see prior power notes; exact Wilcoxon needs n_eff).

## Execution entry

`scripts/level3_pilot_r4/run_micro_r354.py` (mock validated; real gated).

## Handoff

Awaiting Planner review + explicit real-run authorization.
