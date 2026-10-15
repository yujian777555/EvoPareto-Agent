# Phase5-R3-R5-R2 — Initial Audit

**HEAD `8b99b77`** = origin/main · tests green

## Issues found vs instruction

| id | issue | action |
|----|-------|--------|
| A1 | `pre_send_approval` OK when no gate | **fixed** `GateRequired` strict mode |
| A2 | budget errors swallowed in `_send` | **fixed** propagate |
| A3 | ticket used thread-id | **fixed** UUID tickets, settle-once |
| A4 | cap used logical counts | **fixed** `physical_attempts + open tickets` |
| B1 | NSGA-II `_min_rows` default 5-obj | **fixed** ObjectiveSpec |
| C1 | pipeline overwrote PPEC selector | **fixed** keep loop selector |
| D1 | `compute_credit` SPEC_5 default | **fixed** pass `_spec_for_dim` |
| E1 | no exact 2D HV | **added** `hypervolume_2d_mixed` |
