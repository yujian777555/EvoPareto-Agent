# Paired Analysis — 35-Task Parent vs Child

## Results

| | Parent | Child |
|---|---:|---:|
| correct | **29** / 35 | **31** / 35 |
| accuracy | **82.9%** | **88.6%** |
| requests | 35 | 105 |
| cost est | $0.0055302 | $0.0154032 |

## Paired statistics

| | value |
|---|---:|
| child improved | **2** |
| child regressed | **0** |
| both correct | 29 |
| both wrong | 4 |
| net gain | **+2** |
| discordant pairs | 2 |
| McNemar exact p | **0.25** |

## Interpretation

Child accuracy (88.6%) is higher than parent
(82.9%) with net gain +2 and
zero regressions. However, **McNemar exact p = 0.25**
means the difference is **not statistically significant** at n=35.

## Resource comparison

| | Parent | Child |
|---|---|---|
| LLM calls/task | 1 | 3 (self-consistency) |
| total requests | 35 | 105 |
| avg latency | ~4.8s | ~5.5s |

Child uses ~3x the inference calls and ~2x the latency for +2 net correct.
**Cost-effectiveness** must weigh accuracy gain against 3x inference cost.

## Honest caveats

- 35 tasks, +2 net gain, p=0.25 — **not statistically significant**
- Child uses multi-sample self-consistency + explicit answer format — this is
  a **system-level workflow comparison**, not isolated evolutionary attribution
- Some gold answers are non-numeric (fractions, weekdays) where the extractor
  may struggle for both parent and child
- Recursive self-improvement is **NOT** proven by this comparison
