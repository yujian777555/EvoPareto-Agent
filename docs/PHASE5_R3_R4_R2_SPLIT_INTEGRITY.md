# Phase5-R3-R4-R2 — Split Integrity

## P0-1 bug (confirmed at `ff75754`)

```python
split = "eval_out_of_distribution" if self.config.split != "train" else "train"
```

`valid_train` / `valid_seen` were silently mapped to **OOD**.

## Fix

`src/benchmark/split_integrity.py` explicit map:

| user split | train_eval | data dir |
|------------|------------|----------|
| valid_train | train | json_2.1.1/valid_train |
| valid_seen | eval_in_distribution | json_2.1.1/valid_seen |
| valid_unseen | eval_out_of_distribution | json_2.1.1/valid_unseen |

Unsupported split → `SplitIntegrityError` (fail closed).  
`reset()` validates `actual_game_id` contains `/json_2.1.1/{rel}/`.

## Docker verification (2 games × 3 splits)

| requested | resolved train_eval | games in correct dir |
|-----------|---------------------|----------------------|
| valid_train | train | ✅ |
| valid_seen | eval_in_distribution | ✅ |
| valid_unseen | eval_out_of_distribution | ✅ |
| `not_a_split` | — | fail_closed ✅ |

`results/native_alfworld/split_integrity/split_check.json`
