# MICRO-R2 Report (difficulty-stratified)

- Model: `deepseek-flash` real HTTP (direct, proxy bypass)
- Seed: 20260602; train SHA: `17f347dc51477c50…`
- Dev: 5 tasks; Holdout: 8 tasks; S probe: 3 holdout
- Physical requests: **50**/50; cost **$0.009211**/0.05
- Stop: completed

## Dev accuracy

| Cand | Acc |
|---|---:|
| P | 1.00 |
| R | 0.80 |
| F | 0.80 |
| E2 | 1.00 |

**Gen-1 winner (R vs F):** `R`

## Holdout accuracy (paired vs P)

| Arm | Acc | vs P imp/reg | vs winner imp/reg |
|---|---:|---|---|
| P | 1.00 | —/— | —/— |
| R | 1.00 | 0/0 | —/— |
| E2 | 1.00 | 0/0 | 0/0 |
| S | 1.00 | 0/0 | —/— |

## RQ answers (directional only)

1. Children vs Parent on harder tasks: see paired_vs_P; P acc=1.00.
2. Random R=0.8 vs feedback F=0.8 on dev; winner=`R`.
3. E2 vs winner on holdout: imp=0 reg=0.
4. S is a 2-sample voting control (confound isolation); R/F/E2 are single-call. Compare S vs single-call arms carefully.

**No statistical significance. Not recursive self-improvement proof.**

## Notable finding (dev only)

On dev task gsm8k-train-6996 both single-call mutations **R** and **F** were wrong while frozen **P** was correct. The gen-2 child **E2** (instruction mutation from R) answered that same task correctly. So one generation of instruction mutation from a weaker child recovered the Parent-level score on the dev set. On the 8-task holdout all arms were 1.0 — solution-length strata did **not** produce a hard enough slice for deepseek-flash at max_tokens=300.

## Ceiling / budget notes

- Holdout still saturated at 100% across P/R/E2/S; length is a difficulty **proxy** only.
- Request cap hit exactly at 50 (S probe used 6 calls). Cost well under .05.
- A follow-up would need a **hardness-vetted** slice (e.g. known model error rate) rather than solution length alone.

