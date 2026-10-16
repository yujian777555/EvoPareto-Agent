# Compute & API Budget

Assumptions: `deepseek-flash` peak conservative rates **$0.30/1M in ·
$1.20/1M out**; EvalPlus-style task ≈ 2–8k in, 100–400 out ≈ **$0.001–0.003/eval**
(code tasks shorter than ALFWorld episodes). Linear projection — not an invoice.

## Plan A — feasibility pilot (Gate before any claims)

| Item | Value |
|---|---|
| Tasks | 20 (10 HumanEval+ / 10 MBPP+) |
| Genomes | 20 sampled |
| Replicates | 2 |
| Evaluations | **800** |
| Est. tokens in/out | ~2.4M / 0.2M |
| Est. cost | **$0.8 – $2.4** |
| Wall-clock | 2–6 h (rate-limited) |
| Purpose | nonzero pass-rate spread across genomes |

## Plan B — minimal research comparison

| Item | Value |
|---|---|
| Arms | 8 (incl. controls) |
| Population × gens × seeds | 12 × 6 × 3 |
| Tasks / genome | 20 |
| Evaluations | 8×12×6×3 ≈ **1,728** (plus repair) |
| Est. cost | **$3 – $8** |
| Purpose | H1 directional signal |

## Plan C — paper-scale

| Item | Value |
|---|---|
| Arms | 8 |
| Population × gens × seeds | 20 × 12 × 5 |
| Tasks | 50 train / 50 held-out |
| Evaluations | ≈ **9,600** search + 4,000 test |
| Est. cost | **$25 – $70** |
| Wall-clock | 1–3 weeks |

Formulas: `cost ≈ Σ (tin·0.30 + tout·1.20)/1e6`. Bounds: low = short prompts
& early stop; high = beam/verification genes firing. All plans use one SQLite
physical-HTTP ledger; caps fail-closed.
