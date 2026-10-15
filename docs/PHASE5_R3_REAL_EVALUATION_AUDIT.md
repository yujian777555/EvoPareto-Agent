# Phase5-R3 — Real Evaluation Audit (Tasks 2–4)

**Algorithms (NSGA-III / PEEM / PPEC / Genome / objectives): unchanged.**

## Task 2 — Experiment pollution fixes (P0)

| issue | fix |
|-------|-----|
| Real LLM fail → silent Mock | **Removed.** Adapter returns `success=False`, `evaluation_kind=real_llm_failed` |
| Empty/invalid response = success | Backend raises on empty body / empty completion |
| Episode missing provenance | `api_status`, `backend`, `model`, `cached`, `evaluation_kind` on every task |
| Mock auto-fallback in paper runs | `run_real_llm_large` **aborts** if chat probe fails |
| Budget checked after the fact | `assert_budget_before_calls()` **before** requests |

Files: `src/backend/base.py`, `src/benchmark/alfworld_real.py`,
`src/benchmark/webshop_real.py`, `experiments/run_real_llm_large.py`

## Task 3 — Capability prior vs real success (P0)

**Finding:** `_score_completion` uses a hand-designed genome capability prior
(planner/memory/reflection/tool scores). This **dominates** `success` and is
**not** native ALFWorld/WebShop evaluation.

| label | meaning |
|-------|---------|
| `simulated` | MockLLM + synthetic scoring |
| `real_llm_proxy` | real LLM text + synthetic/capability scoring |
| `real_llm_failed` | real call failed; **no success credit** |
| `real_environment` | **not implemented** — native env eval absent |

Docstrings mark scoring as SYNTHETIC/PROXY.  
`src/evaluation/evaluation_kind.py` defines the taxonomy.

**Capability:** we do **not** currently have native ALFWorld/WebShop
environments wired. Real-environment validation is **not available** in this
repo state and must not be claimed.

## Task 4 — Experiment protocol

`experiments/real_eval_protocol.py`:

1. PPEC `accuracy_first` / `cost_first` / `balanced` compared separately
2. Fixed evaluation budget, pre-checked
3. **Independent held-out test** for the selected genome
4. Test uses isolated cache namespace (`seed+10000`) — no train-cache reuse
5. Records API success/fail, tokens, cost

## Task 5 — Acceptance gate

| condition | status |
|-----------|--------|
| DeepSeek valid completion | **FAIL** (200 + 0 body) |
| No mock fallback / invalid success | **PASS** (code fixed) |
| Success not from capability prior | **FAIL** (still proxy; native env missing) |
| Fair real protocol | **PASS** (protocol module ready) |
| Tests green | **PASS** (pytest all green) |

**Decision: do NOT proceed to Phase 5-R3 live tables.** Offline fixes only;
no fake real-LLM results generated.

## Historical result reclassification

| results/ dir | class |
|--------------|-------|
| `ablation/`, `benchmark_extension/`, `real_world/` | **simulated** |
| `final_real_llm/` | **real_llm_proxy** (DeepSeek smoke + proxy scoring) |
| `real_llm_large/` | **simulated_or_pending** (mock-fallback runs; not live evidence) |

## Limitations (paper)

1. No native ALFWorld/WebShop success signals.
2. Capability prior is a design heuristic, not task completion.
3. DeepSeek chat completions unusable at diagnosis time (empty bodies).
