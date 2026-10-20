# Dataset Provenance Audit (Task A)

## Finding

**0/35 R3 questions match official GSM8K test records.**
**35 are synthetic/unmatched.**

| Metric | Value |
|---|---|
| Official source | `https://github.com/openai/grade-school-math/blob/master/grade_school_math/data/test.jsonl` |
| Official file SHA-256 | `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14` |
| Official record count | 1319 |
| R3 task count | 35 |
| Official matches | **0** |
| Synthetic/unmatched | **35** |
| Gold mismatches | 0 |

## Conclusion

The "GSM8K official test split" provenance claim is **NOT verified**. The R3
questions were created from an embedded dictionary in the freeze script and
labeled `gsm8k-test-NNNN` — these are **synthetic GSM8K-style problems**, not
actual official test records. Task IDs do not correspond to official indices.

**Original R3 results are preserved** and relabeled as:
**exploratory workflow comparison on 35 synthetic GSM8K-style tasks**.

They must NOT be interpreted as official GSM8K generalization results.

## Per-task audit table

See `results/level3_pilot_r31/dataset_provenance_audit.json` for the full
35-row table with declared index, match status, gold comparison, and
duplicate check against historical confirmations.
