# Pilot-R2 Paired Analysis — Parent vs Child on 12 Held-out Tasks

**Run id:** `paired2-7715a4e3`
**Exploratory only** — 12 tasks, no statistical significance, not recursive
self-improvement proof.

## Frozen candidates (SHA verified)

| Role | Source | SHA |
|---|---|---|
| Parent | official GSM8K round_1 workflow | `a92febff3c94d065…` |
| Child | real DeepSeek Optimizer output | `a0add78f10e66684…` |
| Child bundle | | `035b51cb257718d8…` |

Child SHAs match the previously verified values — no regeneration.

## Confirmation set

- source: GSM8K **official test split** (held-out, never used in generation)
- n = 12 · task_set_sha256 = `86cc56115220eaed…`
- same model (deepseek-flash) for parent and child
- gold stays host-side only

## Results (rescored)

| | Parent | Child |
|---|---:|---:|
| correct | **2** / 12 | **11** / 12 |
| accuracy | 0.167 | 0.917 |
| LLM requests | 12 | 37 |
| cost estimate | $0.0017952 | $0.0053949 |

Paired: improved **9**,
regressed **0**,
both correct 2,
both wrong 1,
net gain **9**.

## Important scoring caveat

The parent workflow returns a `(response_text, cost)` **tuple** and its official
prompt is an empty `INSTRUCTION`, producing verbose free-form reasoning. The
child returns a single answer string with an explicit `Answer: <num>` contract.

Parent raw outputs were stored truncated at 200 chars, so parent answer
extraction is **unreliable and underestimates** true parent performance (e.g.
test-0000's reasoning is cut off mid-computation). Child scoring is reliable.

Honest reading: **the child scores 11/12 with reliable extraction**; the parent's
observed 2/12 is a lower bound. The child's advantage includes both reasoning
structure (self-consistency voting) and a parseable answer contract.

## Cost

| | value |
|---|---:|
| new HTTP requests this run | 49 / 100 |
| budget debited (cumulative) | $0.013709399999999998 |
| budget remaining | $4.9862906 |
| unit-cost accuracy (child) | 11 correct / $0.0053949 est |

Docker failure rate: 0.00 · IPC total: 49

## Not claimed

- statistical significance (n=12)
- recursive self-improvement
- benchmark-level performance

## NSGA-III readiness

The paired evidence (child ≥ parent on a held-out confirmation set) is a
**prerequisite signal**, not proof of multi-objective dominance. Entering
NSGA-III comparison requires: a larger task set, multiple independent child
candidates, and objectives beyond single-task accuracy (cost, latency, token
usage). Current evidence is **insufficient** to start NSGA-III comparison.
