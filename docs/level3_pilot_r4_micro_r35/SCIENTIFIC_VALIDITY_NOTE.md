# R3.5.2 Scientific Validity Note

## Frozen Parent facts

- `parent_graph.py` uses `Custom(input=problem, instruction="")` — **instruction is empty**.
- `WorkflowProgram.instruction == ""` for the frozen Parent.
- Any F/E2 text is therefore a **new instruction**, not an edit of a non-empty solve prompt.

## What is observed vs not proven

| Statement | Status |
|---|---|
| R3.4 F/E2 **degraded** vs P/R on confirm (0.433/0.333 vs 0.733) | **OBSERVED** |
| Full-instruction overwrite destroyed an original solve strategy | **NOT PROVEN** (Parent had no instruction to destroy) |
| R3.5.1 F_local preserves "original solve logic" | Only means: appends rather than wholesale replace of whatever instruction exists |
| F_old vs F_local difference is solely overwrite vs append | **NOT ISOLATED** — instruction **texts differ** (confounded) |
| E2 can stack identical suffixes | Must record `NO_OP` / `NOT_GENERATED_NO_FAILURE` when no new effective change |

## Protocol implications

1. R3.5.1 tests **coarse-feedback-driven prompt mutation**, not strategy preservation on a rich baseline.
2. Local preservation on a **non-empty** baseline needs a **separate frozen Parent protocol** — do not silently replace the current frozen Parent.
3. F_old vs F_local must be labeled **confounded (different texts)**.

History R3.4 / R3.5.1 records are **not modified**.
