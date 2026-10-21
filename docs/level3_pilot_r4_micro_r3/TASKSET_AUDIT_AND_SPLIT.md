# R3 Task-Set Audit and Split

**Train source:** `results/level3_pilot_r4_data/gsm8k_train_official.jsonl`  
**SHA-256:** `17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465` (7473 rows)

## Historical usage (exclude from new sets)

| Round | Indices |
|---|---|
| MICRO-R1 | 0–7 |
| MICRO-R2 dev | 6245, 499, 6996, 4900, 2518 |
| MICRO-R2 holdout | 3741, 475, 5516, 2354, 1139, 1066, 3324, 7193 |

**21 indices excluded.** Official test / formal confirmation sets are **not** used.

## R3 split (seed `20260603`, disjoint, fixed counts)

| Role | n | Indices |
|---|---:|---|
| **Screening** | 10 | 5895, 1540, 6485, 7068, 7166, 3011, 7396, 6596, 1900, 6752 |
| **Development** | 5 | 4336, 2201, 2495, 5648, 4346 |
| **Confirmation** | 8 | 3098, 6031, 4459, 6404, 2184, 1856, 856, 4627 |

* Mutually exclusive (asserted in `r3_offline_validation.py`).  
* Gold never in candidate prompts.  
* Confirmation outcomes never feed screening / operator design / dev selection.

## R2 stratify defect

R2 `load_and_stratify()` filtered holdout overlap **after** sampling and **refilled** from the pool — this can distort stratum quotas. R3 uses **explicit disjoint sampling with fixed counts** (10/5/8) and asserts uniqueness.

## Difficulty screening — `NO_QUALIFIED_ERROR_ARCHIVE`

Searched repo for historical **model error** records matching current model/prompt/decoder/evaluator. Only generic failure-taxonomy docs found — **no qualified GSM8K error-rate archive**.

`BLOCKED_PENDING_API_AUTHORIZATION` for empirical error-based screening. Proposed screening budget (needs new auth): ~10–20 requests, ~$0.01–0.02 (est.).  
Solution-length tertiles are **difficulty proxies only**, not error rates.
