# Succeed Flag vs Score Delta Discrepancy

n_discrepancies = 2 · causes = {"zero_delta_flagged_succeed": 2}

Both cases are **floating-point epsilon**:

| benchmark | variant | round | flag | delta | classification |
|---|---|---:|---|---|---|
| DROP | graphs | 13 | True | 1.11e-16 | SUCCEED_TRUE_BUT_NOT_UPGRADE |
| GSM8K | ablation_graphs | 17 | True | 2.22e-16 | SUCCEED_TRUE_BUT_NOT_UPGRADE |

AFlow's `succeed = after > before` is true for ε>0; our TOL=1e-9 classifies
them as ties. **No data corruption** — comparison-tolerance difference only.
Official records NOT modified.
