# LEVEL3-PILOT-R4 — Task-Set Freeze Rules and Statistical Analysis Plan

**Status:** DESIGN PREP — PROPOSED freeze, not yet Planner-accepted.
**Baseline commit:** `eaca0b87071fa1387d5bd76a045ce247b568ba65`.
**Companion documents:** `BASELINE_AUDIT.md`, `PREREGISTRATION.md`, `BUDGET_AND_EXECUTION_PLAN.md`.
**No model calls were made to produce this document.**

---

## 1. Data-source verification status

### 1.1 Official GSM8K test split — VERIFIED

| Item | Value | Verified |
|---|---|---|
| Upstream URL | `https://github.com/openai/grade-school-math/blob/master/grade_school_math/data/test.jsonl` | cited |
| Local copy | `results/level3_pilot_r31/gsm8k_test_official.jsonl` | present |
| Byte SHA-256 | `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14` | **YES** (recomputed) |
| Record count | 1319 | **YES** (recomputed) |
| Record schema | question + answer with `####` gold marker | YES |
| Usable for R4 confirmation freeze | **YES** | subject to Planner acceptance |

### 1.2 Official GSM8K train split — **BLOCKED**

| Item | Status |
|---|---|
| Local `train.jsonl` | **NOT PRESENT** anywhere in the workspace |
| `src/benchmark/gsm8k_protocol.py` policy | train = generation/selection only; test = evaluation only |
| Consequence | **Generation-set and development-set freeze cannot be completed** from official train data |

**Blocker statement (explicit):** R4 groups D and E need a train-split generation/development set so that evolutionary or random selection never sees confirmation labels. The official train file is not available locally and its SHA has not been verified here. **This freeze work is paused for generation/dev sets** until the Planner supplies or authorizes acquisition of official `train.jsonl`, after which its SHA and record count must be verified exactly like the test file.

**Not acceptable workarounds (frozen here as prohibitions):**

1. Treating the R3 35 synthetic questions as official GSM8K. They match 0/35 official records.
2. Reusing confirmation tasks for selection.
3. Quietly splitting official **test** into selection+confirmation without a Planner-approved policy deviation recorded in a new preregistration version.

**Allowed alternative (requires Planner decision, default = do not use):** a documented policy deviation where a pre-declared disjoint slice of official test is used for selection and the remainder for confirmation. This weakens the "test is evaluation-only" guarantee and must be labeled as such. Default is to wait for train.

### 1.3 Legacy split manifest warning

`results/stage3_0_p1_r2a/gsm8k_split_manifest.json` assigns search / validation / test all from `gsm8k-test-` ids. That layout predates the provenance audit and must **not** be reused as an R4 freeze. R4 builds new, hashed freeze files under `docs/level3_pilot_r4_design/freeze/`.

---

## 2. Task-set freeze rules

Applies to every role (confirmation now; generation/development when unblocked).

### 2.1 Identity and fields

Every task record must contain exactly these fields:

| Field | Meaning |
|---|---|
| `task_id` | globally unique, stable ID, e.g. `gsm8k-official-test-0123` |
| `question` | original prompt text, unmodified |
| `gold_answer` | canonical gold after extraction rule |
| `source` | provenance string (dataset + split + file SHA) |
| `split` | `train` or `test` |
| `index` | 0-based index in the official file |

### 2.2 Normalization and dedup

| Rule | Specification |
|---|---|
| Gold extraction | text after the **last** `####` marker in `answer` |
| Whitespace | collapse runs of whitespace to a single space; strip ends |
| Empty question/gold | rejected at freeze time |
| Duplicate `task_id` | rejected at freeze time |
| Duplicate question text | reported; rejected by default |
| Unicode | UTF-8; keep official bytes for question text |
| Scoring equality | project extractor; exact match on canonical gold after normalization |

### 2.3 Hashing — **canonical serialization (R4-RF unified)**

Exactly **one** rule is authoritative. Implementation: `src/research/r4_paired_stats.canonical_task_set_sha256`.

| Knob | Frozen value |
|---|---|
| Task order | sort by `task_id` ascending (lexicographic / code-point) |
| Per-task fields | JSON array `[task_id, question, gold_answer]` in that order |
| Outer structure | JSON array of those arrays |
| `json.dumps` kwargs | `ensure_ascii=False`, `separators=(",", ":")`, `sort_keys=False` |
| Text encoding | UTF-8, no BOM |
| Digest | SHA-256, lowercase hex |

Reference implementation:

```python
ordered = sorted(
    ((t["task_id"], t["question"], t["gold_answer"]) for t in tasks),
    key=lambda x: x[0],
)
payload = [[tid, q, g] for tid, q, g in ordered]
blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
sha = hashlib.sha256(blob).hexdigest()
```

**Historical note (do not mix):** v0 (`confirmation_set_proposed.json`) hashed the same tuples with default `json.dumps` separators `', '` / `': '` and no explicit task sort. That digest (`4885c977…`) is kept as `legacy_v0_sha` for audit only. v1 uses the canonical rule below. Changing the rule voids both.

### 2.4 Gate order at run time (reuse R3 discipline)

1. Field completeness -> 2. ID uniqueness -> 3. ordering / count -> 4. recomputed SHA == declared SHA -> 5. declared SHA == expected SHA embedded in the runner -> 6. only then may credentials / HTTP / budget be touched.

Existing implementation to extend: `verify_taskset()` in `scripts/level3_pilot_r3/run_paired_35.py`, covered by `tests/baseline_first/test_r31r1_hash_gate.py`.

### 2.5 Immutability after freeze

Any edit produces a **new version** (`R4-confirm-v1-...`), a new SHA, and requires Planner re-approval. Silent edits are a protocol violation.

---

## 3. Proposed confirmation freeze (v1 after contamination audit)

**Files:**

| Version | Path | `task_set_sha256` | Status |
|---|---|---|---|
| v0 (legacy hash) | `docs/level3_pilot_r4_design/freeze/confirmation_set_proposed.json` | `4885c9771a53ad1adc2c0bffaff738e4aed3d0de434f9a39a17cba1fdba6204d` | superseded, **preserved** |
| **v1 (canonical)** | `docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json` | `1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4` | **PROPOSED_PENDING_PLANNER_ACCEPTANCE** |

| Item | Value |
|---|---|
| Version | `R4-confirm-v1-proposed` |
| Membership change vs v0 | **NONE** (contamination audit found 0 contaminated tasks) |
| Hash change vs v0 | serialization only (canonical rule) |
| Population | official GSM8K test.jsonl (1319 records) |
| Selection | `random.Random(20260601).sample(range(1319), 40)`, then sort by index |
| `n_conf` | **40** |
| Official file SHA (recomputed in R4-RF) | `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14` |
| Selection uses confirmation labels? | **NO** |
| Groups sharing this set | A, B, C, D, E |
| Contamination verdict | `CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH` (see `CONFIRMATION_CONTAMINATION_AUDIT.md`) |
| Prior model-scored official indices (not in this set) | 1, 2 (R2) |

**Exclusion rule (pre-declared, applied):** drop any official index whose question text appears in prior model scoring/selection/debug artefacts. Result: 0 exclusions. No performance-based redraw.

**Note on n_conf = 40.** Proposed size, not chosen to force significance. See section 5. Remaining quota (56) cannot host A–E (480 calls) — see `BUDGET_AND_EXECUTION_PLAN.md`.

## 4. Statistical analysis plan (frozen at execution)

### 4.1 Primary outcome

`correct` in {0,1} via host-side gold comparison. Any of `invalid_output`, `timeout`, `execution_failure` scores **0** and stays in the denominator.

### 4.2 Paired cell counts (for each contrast X minus A)

| Cell | Symbol |
|---|---|
| X correct, A wrong | `b` (improved) |
| X wrong, A correct | `c` (regressed) |
| both correct | `n11` |
| both wrong | `n00` |

Report `b`, `c`, `n11`, `n00`, `n = b+c+n11+n00`, net gain `b-c`.

### 4.3 Hypothesis tests

| Test | Specification |
|---|---|
| Primary | **Exact McNemar**, two-sided, on `(b, c)` |
| Exact definition | Let `D = b+c`. Under H0, `b ~ Binomial(D, 0.5)`. Two-sided exact p = min(1.0, 2 * min(P[X<=min(b,c)], P[X>=max(b,c)])). Also report the one-sided tail `P[X <= min(b,c)]` as descriptive only. |
| One-sided tests | **Not used for confirmatory claims.** |
| Multiplicity | Holm-Bonferroni over family {B-A, C-A, D-A, E-A, E-D} at FWER 0.05 |
| Method switching | forbidden after data; a deviation voids the confirmatory label |

**Historical note.** R3 reported `mcnemar_exact_p = 0.25` with `b=2,c=0`. That value is the **one-sided** tail. The two-sided exact value is **0.50**. Both are non-significant. R4 reports both and treats two-sided as confirmatory.

### 4.4 Effect sizes and intervals

| Quantity | Method |
|---|---|
| Accuracy per group | `correct / n` with **Wilson 95% CI** |
| Paired risk difference `(b-c)/n` | Newcombe paired-score CI (preferred) |
| Matched odds ratio `b/c` | when `c>0`; if `c=0`, Haldane-Anscombe `(b+0.5)/(c+0.5)` labeled approximate |
| McNemar effect (Cohen g) | `b/(b+c)` descriptively when `b+c>0` |

### 4.5 Missing data and failures

| Case | Rule |
|---|---|
| API/HTTP failure after frozen retry policy | score incorrect; mark `execution_failure`; keep row |
| Container `CONTAINER_NOT_CREATED` | cannot score -> incorrect + `execution_failure` |
| Unparseable model output | incorrect + `invalid_output` |
| Duplicate `task_id` in output | **invalidates the run file**; do not average; abort analysis |
| Missing task row | treated as incorrect + `missing`; reported in the completeness table |
| Dropping rows to improve accuracy | **prohibited** |

### 4.6 Budget / integrity checks in analysis

Before any p-value is printed, the analysis tool must verify:

1. Task-set SHA matches the freeze file.
2. All groups used the same confirmation IDs (set equality).
3. Frozen results snapshot unchanged (`tests/frozen_guard.py`).
4. Request counts in the report equal ledger totals.
5. Simulated/mock rows are not present (or are excluded and counted).

---

## 5. Sample-size estimation (assumptions first)

We do **not** pick an N that is guaranteed to reach significance. We state assumptions, give ranges, and accept that the current quota may be insufficient.

**Model.** For paired binary outcomes with discordance `d = p01 + p10` and net effect `delta = p01 - p10`, the normal-approximation size for a two-sided McNemar test is:

```
n ~= ( z_{1-alpha/2} * sqrt(d) + z_{1-beta} * sqrt(d - delta^2) )^2 / delta^2
```

with `z_{0.975} = 1.96`, `z_{0.80} = 0.84` for alpha=0.05, power=0.80.

### 5.1 Required n under different effect assumptions
| Scenario | p01 (improve) | p10 (regress) | net delta | approx n (power 0.80, alpha=0.05 two-sided) |
|---|---:|---:|---:|---:|
| small net +2% | 0.03 | 0.01 | +0.02 | 783 |
| R3-like: all discordant favorable +5% | 0.05 | 0.00 | +0.05 | 155 |
| moderate +3% | 0.05 | 0.02 | +0.03 | 609 |
| moderate +6% | 0.08 | 0.02 | +0.06 | 216 |
| clear +8% | 0.10 | 0.02 | +0.08 | 145 |
| strong +9% | 0.12 | 0.03 | +0.09 | 143 |
| large +12% | 0.15 | 0.03 | +0.12 | 96 |
| very large +14% | 0.18 | 0.04 | +0.14 | 86 |

**Reading.** Detecting a net +5% improvement (R3-scale, with zero regressions) needs on the order of **~155 paired tasks**. Detecting a net +12% needs ~96. These are the honest scales. An N of 35-40 is only enough to detect **large** effects or to estimate rates with wide CIs.

### 5.2 Approximate power at candidate N
| n_conf | delta=+5% (p01=.05,p10=0) | delta=+8% (p01=.10,p10=.02) | delta=+12% (p01=.15,p10=.03) |
|---:|---:|---:|---:|
| 20 | 0.17 | 0.18 | 0.24 |
| 35 | 0.26 | 0.28 | 0.39 |
| 40 | 0.29 | 0.31 | 0.43 |
| 60 | 0.41 | 0.43 | 0.59 |
| 80 | 0.52 | 0.54 | 0.72 |
| 120 | 0.69 | 0.72 | 0.87 |
| 160 | 0.81 | 0.83 | 0.95 |

### 5.3 Consequences for R4 design

| Implication | Action |
|---|---|
| R3-scale effects (+2/35) are far below detection at N~40 | R4 must either increase N (budget), or declare the study as **estimation/ablation** (report CIs, not binary discovery) |
| Full A-E at N=40 needs >= 200 confirmation calls (and more for B's k samples and D/E candidates) | does not fit in remaining 56-request quota -> **new authorization required** (`BUDGET_AND_EXECUTION_PLAN.md`) |
| If authorization stays at 56 requests | only a **strict subset** can run; the study is labeled `INCOMPLETE` / `UNRESOLVED` for the missing contrasts — hypotheses are not silently dropped |

**Frozen stance:** primary analysis is paired and two-sided; N is justified by the assumed effect sizes above; any N change requires a new preregistration version.

---

## 6. Deliverable checksums (this round)

| Artefact | Value |
|---|---|
| Confirmation freeze file (v1) | `docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json` |
| Confirmation `task_set_sha256` (v1 canonical) | `1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4` |
| Confirmation `task_set_sha256` (v0 legacy) | `4885c9771a53ad1adc2c0bffaff738e4aed3d0de434f9a39a17cba1fdba6204d` |
| Official test file SHA | `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14` |
| Official train file | **UNAVAILABLE — BLOCKED** |
| New real API requests this round | **0** |

