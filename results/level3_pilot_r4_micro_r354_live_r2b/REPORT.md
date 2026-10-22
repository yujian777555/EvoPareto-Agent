# MICRO-R3.5.4 mechanism isolation

Mode: **REAL**

- B base text sha=74939992a50237b4…
- feedback=ANSWER_MISMATCH id=1166d372b0f26a1a src=['gsm8k-train-2364', 'gsm8k-train-5317']
- A/O same text=True
- confirm={'B': 0.8333333333333334, 'A': 0.8333333333333334, 'O': 0.8666666666666667}
- paired={"A_vs_B": {"both_correct": 25, "both_wrong": 5, "improved": 0, "mcnemar_exact_p_two_sided": 1.0, "n": 30, "regressed": 0, "status": "COMPLETE"}, "A_vs_O": {"both_correct": 24, "both_wrong": 3, "improved": 1, "mcnemar_exact_p_two_sided": 1.0, "n": 30, "regressed": 2, "status": "COMPLETE"}, "O_vs_B": {"both_correct": 24, "both_wrong": 3, "improved": 2, "mcnemar_exact_p_two_sided": 1.0, "n": 30, "regressed": 1, "status": "COMPLETE"}}
- holm={"A_vs_B": {"p_holm": 1.0, "p_raw": 1.0, "reject_0_05": false}, "A_vs_O": {"p_holm": 1.0, "p_raw": 1.0, "reject_0_05": false}, "O_vs_B": {"p_holm": 1.0, "p_raw": 1.0, "reject_0_05": false}}

**Exploratory. Not RSI proof.**


## Interpretation (exploratory, single seed)

1. **A vs O (primary):** +1/−2, McNemar p=1.0 — **no detectable difference** between append and replace at n=30.
2. **A vs B:** 0/0 — append neither helped nor hurt vs base strategy.
3. **O vs B:** +2/−1, p=1.0 — replace slightly higher (0.867 vs 0.833) but not significant.
4. Same feedback text/ID/source confirmed; A kept prefix, O did not.
5. **Not RSI / not NSGA-III / not cross-seed / not GSM8K-general.** n.s. does not mean mechanisms equivalent.

## Deviations from preregistration

- Calibration stage marked NOT_EXECUTED_IN_ENTRY (frozen but unused).
- Single seed only (multi-seed plan not run).
