# Planner Handoff — Stage 3.0-P1-R2A-R2

**FINAL_DECISION: READY_FOR_LEVEL3_LIVE_APPROVAL**

## Three proof obligations

1. **Untrusted Workflow cannot harm the host via IPC** — request-id allowlist,
   path containment, symlink refusal, atomic O_EXCL handoff, trusted model
   only; 10 negative classes tested with zero model calls on reject.
2. **No real request can break the hard caps** — pre-send token bound,
   cumulative token quotas (atomic, restart-safe), worst-case cost
   reservation, 300-request cap, $5 cap; uncertain billing blocks persistently.
3. **Official AFlow runs the full search+evaluation path on real GSM8K-style
   questions** — Optimizer + parent selection + validated mutation + Docker
   child + IPC + gold scoring + experience + persistence, all in one run.

## Caveat to decide

AFlow optimizer prompts exceed the frozen 2000 input-token cap (measured
~6049). The gate correctly blocked rather than truncating. Before the live
pilot, confirm whether `MAX_INPUT_TOKENS_PER_REQUEST` should be raised (the
$5 budget already assumed 2000; a raise needs a re-derived worst case).

## Caps (unchanged)

deepseek-flash · GSM8K train 0-19 search / train 20-29 val / test 0-19 final ·
3 rounds · 300 HTTP · 2M/200k tokens · **$5** · peak cache-miss pricing.

## Request

Approve the $5 DeepSeek micro-pilot (or return the token-cap adjustment).
Executor will not call the real API without explicit authorization.
