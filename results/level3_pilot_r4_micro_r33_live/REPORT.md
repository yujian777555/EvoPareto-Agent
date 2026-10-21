# MICRO-R3.3 run report

Mode: **REAL DeepSeek model**

- requests=26
- actual known cost USD=0.00589920
- budget charged upper bound USD=0.00589920
- gen-1 winner=R; dev scores={'R': 1.0}
- confirmation paired analysis={"P_vs_winner": {"base_accuracy": 1.0, "base_only_correct": 0, "both_correct": 8, "both_wrong": 0, "candidate_accuracy": 1.0, "candidate_only_correct": 0, "interpretation": "EXPLORATORY_ONLY_NOT_CONFIRMATORY", "mcnemar_exact_p_two_sided": 1.0, "n": 8}}

This is an exploratory GSM8K micro-pilot only. Mock results are not model-performance evidence. Eight confirmation tasks do not support a confirmatory recursive-self-improvement claim.


## Interpretation (exploratory)

1. **Child vs Parent:** winner R vs P on 8 confirm tasks: both 1.0, improved 0 / regressed 0, McNemar exact two-sided p=1.0. No improvement observed.
2. **Random vs feedback mutation:** Parent dev was 5/5, so no FailureRecord existed. F was **explicitly FAILED** (NO_USABLE_FEEDBACK) — protocol did not fabricate feedback. R (OP_ERROR_RECOVERY) was the only gen-1 candidate and became winner.
3. **E2:** failed the same way — winner R was perfect on dev (NO_FAILURE), so E2 had no usable feedback and was **not** created (slot retained as FAILED). E2 therefore did not inherit any improvement.
4. **Voting confound:** R and P are single-call arms; no S probe was executed this run (26 of 50 planned calls used). No evidence of single-call advantage.
5. **Ceiling / sample:** 8 confirm tasks, all correct for both arms. Differences would be undetectable here; absence of effect is **not** evidence of equivalence.

## Cost

26 physical requests, known cost .0058992 (billing_uncertain=false). Within 55 / .05 caps.

## Next-step recommendation

- Use a **harder** confirmation slice (model error rate > 0 on Parent) so paired deltas are observable.
- If no Parent failures on dev, F/E2 cannot generate candidates by design — consider a slightly harder **dev** slice or a declared cold-start policy (pre-registered), not post-hoc feedback invention.
- Multi-seed paired study only after a non-degenerate slice exists.

**Not RSI proof. Not confirmatory.**
