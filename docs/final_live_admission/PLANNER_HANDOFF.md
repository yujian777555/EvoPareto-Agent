# Planner Handoff — Final Evidence & Budget Correction

## Three obligations

1. **No answer leakage** — task payload is `['task_id', 'question']`;
   gold stays in the host scorer. `True`
2. **Real candidate closed loop** — Optimizer candidate SHA
   `d4c8ac1f33dcf4ab…` equals the executed child
   SHA; official `experience.json` + `results.json` written by AFlow utilities;
   2 real Mock HTTP POSTs through the
   budget gate.
3. **Atomic worst-case reservation** — `res_cost` now enters the SQLite
   transaction; low-budget regression proves refusal before send. Token-limit
   proposal filed (8000 in / 500 out; 300-request worst case
   $0.9 < $5) and
   **does not change pilot authorization**.

## Caps (unchanged until Planner approves the proposal)

deepseek-flash · 3 rounds · **300 HTTP** · **2M/200k tokens** · **$5** ·
peak cache-miss pricing · GSM8K train/test split frozen.

## Request

Approve the $5 micro-pilot and the 8000-input-token cap adjustment (or reject
the adjustment and keep 2000, accepting that optimizer prompts will be blocked).
Executor will not call the real API without explicit authorization.
