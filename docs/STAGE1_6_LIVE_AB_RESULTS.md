# Stage 1.6 Live A/B Results

**Execution SHA:** `f73299189c2b5bd92569c1b15f108e2eec9f7b38`  
**Episodes:** 12/12 completed once each · **Successes: 0 (both arms)**

---

## Headline

| Arm | n | won | mean cost | mean tokens_in | mean steps | mean loop occ. | rep. ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 6 | **0** | $0.00295 | 9,252 | 29.3 | 18.3 | 0.796 |
| shared_repaired | 6 | **0** | $0.00363 | 11,437 | 30.0 | **18.3** | 0.772 |
| **Δ** | — | 0 | +23% | +24% | +0.7 | **0** | −0.024 |

`cost_per_success` = **undefined** for both arms (no successes; not 0).

## Paired (task × repeat)

| metric | value |
|---|---:|
| paired_repaired_only_wins | **0** |
| paired_current_only_wins | **0** |
| paired_ties | **6** |

All six pairs failed in both runtimes.

## Loop / exploration (Gate 4, auxiliary)

- Loop occurrences **identical** (18.3 / episode) — stagnation warning did not
  change the loop rate at n=2 repeats.
- Repetition ratio marginally lower in repaired (0.77 vs 0.80).
- Repaired prompts are longer (progress block) → +24% input tokens.

## Budget / ledger

| Item | Value | Cap |
|---|---:|---:|
| Physical HTTP | **360** | 400 |
| Input tokens | ~124k | — |
| Output tokens | 1,872 | — |
| Estimated cost | **$0.03949** | $0.08 |
| settled ok/failed | 360 / 0 | — |
| retries / billing_blocked | 0 / false | — |

## Gate decisions

| Gate | Result |
|---|---|
| G1 repaired solvability | **FAIL** (0/6) |
| G2 paired improvement | **REPAIR_NOT_SUPPORTED** (0 vs 0, 6 ties) |
| G3 cost safety | **PASS** (ratio 1.22 ≤ 1.5) |
| G4 loop reduction | no improvement in loop occurrences |

## Honest limits

- n=2 repeats are not controlled RNG replicates (no LLM seed).
- One progress-block template; does not prove no other repair could work.
- Expert sequences (Gate C) show the env is solvable — the **policy** is the gap.
