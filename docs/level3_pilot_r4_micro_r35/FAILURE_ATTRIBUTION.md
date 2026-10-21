# R3.5 Failure Attribution (from real R3.4 artifacts)

**Source commit:** `6d8107df…` · No history modified

## 1. What ran

| Arm | Operator / source | Confirm acc | Wrong |
|---|---|---:|---:|
| P | frozen graph | 0.733 | 8 |
| R | random `OP_ERROR_RECOVERY` | 0.733 | 8 |
| F | feedback → `OP_ARITH_RECHECK` | 0.433 | 17 |
| E2 | winner(F/R) + `OP_ARITH_RECHECK` again | 0.333 | 20 |

Real FailureRecords: calibration 2 errors, dev Parent 2 errors → F/E2 **were** feedback-driven (not fabricated).

## 2. Code-level mechanism

`apply_random_mutation` / `build_feedback_child` call `mutate_insert_instruction`,
which **replaces** the entire `instruction` literal.  
`OP_ARITH_RECHECK` pool text (“Compute, then re-add the key numbers once…”) **discards** the original solve instruction.

E2 applies the same operator class on top of an already rewritten instruction → compounding.

## 3. Hypotheses (not conclusions)

| ID | Claim | Evidence status |
|---|---|---|
| **H1** | Over-constrained verify prompts cause degradation | **Pattern supported** (acc collapse) |
| **H2** | Error attribution quality too coarse | Untested (only `ANSWER_MISMATCH`) |
| **H3** | Mutation destroyed original solve logic | **Pattern supported** (full overwrite) |
| **H4** | Seed randomness | Open (R≈P; F/E2 large consistent drop) |

## 4. Checks

* Confirm set not used for selection: `None`  
* Gold never in candidate prompts  
* Failures are answer errors (exec flags true; not parse/harness)

## 5. Repair direction

`F_LOCAL` = **append-only** verification suffix; keep original instruction prefix;
record `FeedbackDiagnosis`; `NO_OP` if nothing changes; `NO_USABLE_FEEDBACK` if no real failures.
