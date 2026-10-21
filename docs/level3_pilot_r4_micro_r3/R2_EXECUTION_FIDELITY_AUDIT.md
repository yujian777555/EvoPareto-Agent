# R2 Execution Fidelity Audit (MICRO-R3-OFFLINE)

**Status:** `EXECUTION_FIDELITY_GAP` **CONFIRMED**  
**Baseline:** `7da1c8d426ce2ab85c91eba3879936ebccbc5caf`  
**Real API this round:** **0** · Cost **$0**

## Finding

`scripts/level3_pilot_r4/run_micro_r2.py` → `run_prog()`:

```python
prompt = f"{instr}\n{q}\nEnd with 'Answer: <num>'."
r = real_chat(prompt, ...)
```

It reads `prog.instruction` only. It **never** `compile_graph_source(prog)` / `exec`s the candidate graph. Therefore:

| Question | Answer |
|---|---|
| Did P run the frozen Parent workflow? | **NO** — only Parent-style empty instruction + question via direct LLM call |
| Did R/F/E2 run their mutated graphs? | **NO** — only their mutated **instruction strings** |
| Did graph structure / control flow participate? | **NO** |
| Does lineage match what ran? | **Partially** — instruction text matches; **graph_source was unused** |
| Was Parent vs child only an instruction A/B? | **YES** |

## What R2 data can support

* Valid: real DeepSeek responses to **prompt variants** on frozen train slices; request/cost ledger is real.
* **Not valid as:** evidence that workflow-graph mutations improved agents; evolutionary graph search; recursive self-improvement.

Raw R2 artifacts are **preserved unchanged** under `results/level3_pilot_r4_micro_r2/`.

## Fix (R3 offline)

`src/research/r3_mutation_feedback.execute_candidate()` always runs **compiled `graph_source`** via `execute_program_locally` (with AFlow mock stubs offline). Offline validation shows:

* `executed_graph_source=True` for Parent and child  
* Parent graph SHA matches frozen `a92febff…`  
* Child SHA differs and mock behavior **differs** with instruction  
* Same seed → same child hash (reproducible)  
* Feedback summary drives operator selection; no-feedback → explicit `NO_USABLE_FEEDBACK` failure  
* E2 parent_program_id = gen-1 winner; generation=2

## Label

`EXECUTION_FIDELITY_GAP` on R2; R3 unified executor is the repair path before any new real-model comparison.
