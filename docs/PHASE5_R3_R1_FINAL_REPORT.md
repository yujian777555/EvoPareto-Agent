# Phase5-R3-R1 — Final Report

**Stage verdict: `BLOCKED`**  
(offline protocol fixed; native env + live LLM still unavailable)

---

## 1. GitHub status

| item | value |
|------|-------|
| local HEAD | `941202a` → this commit |
| remote | `origin/main` synced at start |
| working tree | clean after commit |

## 2. Code fixes

| file | problem | fix | tests |
|------|---------|-----|-------|
| `src/runtime/task_split.py` | test = same 5 templates, new seed | `task_fingerprint`, content split, leak detector | `test_r3r1_protocol.py` |
| `experiments/real_eval_protocol.py` | always `fitness_vector[0]` | `select_by_preference` via PSS | `test_preference_selection_not_always_fitness0` |
| `src/runtime/behavioral_agent.py` | genome = prompt tags | MemoryStore / reflection / tool allowlist / BudgetMeter | behavior tests |
| `src/backend/diagnostics.py` | field-presence balance; len-based chat | parse `is_available`, parse `choices.message.content` | suite green |
| `run_real_llm_large.py` | mock fallback | abort on API fail; pre-budget | `test_real_eval_safety.py` |

## 3. Native ALFWorld

| question | answer |
|----------|--------|
| real integration? | **NO** — `NATIVE_ENV_BLOCKED` |
| reset/step? | **NO** |
| multi-step env loop? | **NO** (local BehavioralAgent only) |
| success from env? | **NO** |
| simulator/人工评分? | **YES** (capability prior) — labeled PROXY |

Install failed on Windows (metadata-generation-failed / ai2thor).

## 4. Agent Genome

| dimension | behavioral? |
|-----------|-------------|
| planner_strategy | YES (step structure) |
| memory_strategy | YES (read/write gates) |
| reflection_strategy | YES (retry path) |
| tool_policy | YES (allowlist) |
| reasoning_budget | YES (BudgetMeter) |

No `PROMPT_ONLY` remaining in BehavioralAgent; adapter scoring still PROXY.

## 5. PPEC

- Selection now uses **Preference Satisfaction** (cost-aware).
- accuracy vs cost preference selects **different** genomes (tested).
- Reference-direction niching unchanged in NSGA-III core; PPEC uses
  `PreferenceAwareNSGA3` (direction adaptation). Full env-selection A/B
  still needs native env for final claim.

## 6. API

| check | result |
|-------|--------|
| valid completion | **FAIL** (200 + empty body) |
| mock fallback | **removed** |
| live success calls | **0** |
| budget gate | pre-request + tests |

## 7. Tests

`pytest` → **all green** (including new R3-R1 suites).  
Native env integration tests: **N/A (blocked)**.

## 8. Paper validity

| class | artifacts |
|-------|-----------|
| usable now | synthetic algorithm evidence (NSGA-III/PEEM/PPEC), operator utility figs, audits |
| simulated | `results/ablation`, `benchmark_extension`, `real_world`, `real_llm_large` |
| real-LLM proxy | `results/final_real_llm` smoke only |
| must re-run | any “real agent” claims; native ALFWorld/WebShop tables |

## 9. Stage conclusion

**`BLOCKED`**

Reasons: (1) DeepSeek chat returns no completion content; (2) native ALFWorld
not installed; (3) success scoring remains capability-prior proxy.

Offline protocol correctness is improved; live/native experiments must not be
claimed until Stage B/C gates open.

---

## Deliverables

- `docs/PHASE5_R3_R1_INITIAL_CODE_AUDIT.md`
- `docs/PHASE5_R3_R1_NATIVE_ENV_AUDIT.md`
- `docs/PHASE5_R3_R1_GENOME_BEHAVIOR_AUDIT.md`
- `docs/PHASE5_R3_R1_BASELINE_FAIRNESS_AUDIT.md`
- `docs/PHASE5_R3_R1_FINAL_REPORT.md`
- source fixes + regression tests

**Principle honored:** no contaminated positive results; no algorithm/task
scoring changes to inflate metrics.
