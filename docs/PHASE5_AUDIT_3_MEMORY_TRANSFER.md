# Phase5-Audit-3 — PEEM Memory Transfer

**Priority:** P1 · **Status:** COMPLETE · **Algorithms:** unchanged

## Question

Does PEEM learn **reusable evolutionary knowledge**, or only benchmark-specific
operator statistics?

## Protocol

| stage | detail |
|-------|--------|
| Train | PEEM experience on **ALFWorld** (3 seeds) |
| Test | **WebShop** |
| Arms | 1) Random mutation  2) Fresh PEEM  3) Transferred PEEM memory |
| Budget | identical (μ=12, G=6, tasks=8) |

## Results (`results/audit/peem_transfer.json`)

| Mode | Success | HV |
|------|---------|-----|
| Random | 0.375 ± 0.031 | 0.125 ± 0.010 |
| Fresh PEEM | **0.420 ± 0.040** | **0.171 ± 0.017** |
| Transferred PEEM | **0.420 ± 0.034** | 0.140 ± 0.033 |

## Verdict

- Transfer **≥ random** on success — memory is not harmful and keeps gains.
- Transfer **= fresh PEEM** on success — reusable algorithmic prior.
- Transfer **< fresh** on HV (−0.031) — utility scores are **partially
  benchmark-specific**; refilling memory on the target domain recovers HV.

**Interpretation:** PEEM learns *transferable search bias* (which operator
classes to favor) more than portable numerical credit values.

## Limitations

1. Single transfer pair (ALFWorld→WebShop); more pairs needed for generality.
2. Mock-LLM accounting; real-LLM transfer not yet run.
3. Injecting memory replaces the experience object; refit speed on target
   domain is untested.
