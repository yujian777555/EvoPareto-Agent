# LEVEL3-PILOT-R4 Micro Exploratory Report

- Model: `deepseek-flash` (real HTTP, proxy bypass direct)
- Dev: 5 tasks ['gsm8k-train-0000', 'gsm8k-train-0001', 'gsm8k-train-0002', 'gsm8k-train-0003', 'gsm8k-train-0004']
- Holdout: 3 tasks ['gsm8k-train-0005', 'gsm8k-train-0006', 'gsm8k-train-0007']
- Physical requests: **34** / 50
- Actual cost: **$0.006092** / $0.05
- Tokens in/out: 2363 / 4486
- Stop reason: completed

## Dev accuracy (candidate selection)

| Candidate | Dev acc |
|---|---:|
| P | 1.00 |
| C1 | 1.00 |
| C2 | 1.00 |
| C3 | 1.00 |

**Gen-1 winner:** `P`

## Holdout accuracy (3 tasks, paired)

| Arm | Acc | vs Parent improve/regress | vs winner improve/regress |
|---|---:|---|---|
| P (Parent) | 1.00 | — | — |
| P | 1.00 | 0/0 | — |
| C3 | 1.00 | 0/0 | 0/0 |

## Interpretation (directional only)

1. First-gen vs Parent: improved 0, regressed 0.
2. Second-gen vs first-gen winner: improved 0, regressed 0.
3. Improved ids: []; regressed ids: [].
4. Cost must be weighed against these tiny deltas (n=3 holdout).
5. **No statistical significance. Not recursive self-improvement proof.**

## Ceiling effect and design note

All 4 candidates scored **5/5 on dev** and **3/3 on holdout**. Tie-break by fixed order selected **P** as gen-1 winner, so C3 is a second-gen **instruction mutation from Parent** (not from C1/C2). Holdout comparison is therefore P vs C3 (and P was scheduled twice in the arm list, yielding 6 P holdout calls — recorded honestly in the ledger as hold:P ×6).

On this easy first-8-train slice there is **no headroom** to distinguish mutations. Directional reading: mutations did not hurt; they also did not help. A non-trivial dev/holdout slice would be required to observe lineage effects.

## Next step suggestion

If a follow-up micro-run is authorized, use harder GSM8K train indices (e.g. a random slice with mixed difficulty) while keeping the same 50-request/.05 envelope, so accuracy is not pinned at 1.0.


## Files

- `protocol.json`, `candidate_lineage.json`, `request_ledger.json`, `paired_results.json`, `summary.json`
