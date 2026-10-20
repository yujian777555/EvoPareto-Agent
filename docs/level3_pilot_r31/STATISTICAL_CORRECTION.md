# Statistical Correction (Task C)

## Recomputed from raw paired records

| Metric | Value |
|---|---:|
| Parent correct | 29/35 |
| Child correct | 31/35 |
| improved | 2 |
| regressed | 0 |
| both correct | 29 |
| both wrong | 4 |
| net gain | +2 |

## McNemar: one-sided vs two-sided

| | value |
|---|---|
| discordant pairs (b + c) | 2 |
| one-sided p | **0.25** |
| two-sided p | **0.5** |

For b=2, c=0: one-sided p=0.25 (child better), two-sided p=0.50.
The R3 report cited one-sided p=0.25. **Neither reaches significance.**
The distinction is now explicit.

## Preregistration timing

Git history cannot prove temporal ordering within a single commit. The preregistration-before-calls claim is NOT independently verified.
