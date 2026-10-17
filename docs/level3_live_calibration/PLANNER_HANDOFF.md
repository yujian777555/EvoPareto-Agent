# Planner Handoff — Level 3 Live Calibration

## What this run proved (real DeepSeek)

1. **Real model reachable and compliant** — `deepseek-flash`
   (DeepSeek-V4.1-Flash-1017) returned real reasoning; thinking disabled
   accepted; `finish_reason=stop`.
2. **Real GSM8K math works** — non-empty, parseable, predicted `10` (correct
   for the train problem).
3. **Real Optimizer XML generation works** — complete `<modification>/<graph>/
   <prompt>`, graph compiles, `class Workflow` present.
4. **Budget gate held on real traffic** — 2 HTTP
   requests, 2 ledger rows, **$0.0005934**
   actual (cap $0.10). HTTP==ledger.

## What failed (honest)

**Docker child execution FAILED** with `NameError: name 'INSTRUCTION' is not
defined`. Root cause: the real model's `<prompt>` field was
`FAIL:invalid syntax`, so the generated `prompt.py` could not provide the
module-level `INSTRUCTION` the generated `graph.py` expects.

This is a **real calibration finding** about the Optimizer output contract —
not a mock artifact. Per the stop rules, the run halted here
(`STOP_REASON=DOCKER_CHILD_EXECUTION_FAILED`) and consumed **no further real quota**.

## Budget used vs authorized

| | authorized | used |
|---|---:|---:|
| requests | 10 | 2 |
| cost | $0.10 | $0.0005934 |
| input tokens | 80000 | 651 |
| output tokens | 5000 | 1000 |

Remaining headroom was **not** spent on self-repair retries.

## Recommendation

Before the full $5 pilot, decide how to handle Optimizer `<prompt>` output that
is not valid Python (e.g. wrap as `INSTRUCTION = <repr(text)>` on write, or
reject and retry under budget). Then authorize the next calibration slice or
the full pilot.
