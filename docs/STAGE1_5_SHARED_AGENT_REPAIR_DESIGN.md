# Stage 1.5 Shared Agent Repair Design

**Rule:** one shared execution-layer baseline for **all** evolutionary arms.
No PEEM/PPEC-only boost. 0 real API this round.

---

## Why repair is needed

Native positive controls prove the environment is solvable in 7–18 steps.
LLM agent (0/18) fails to organize the multi-step relation. Root gaps:

1. Memory stores only the last observation preview (no action/feedback).
2. No persistent goal-state (holding X? light on? X at target?).
3. Stagnation (`examine desk 1`×N) is invisible to the agent.

## Mechanism candidates

| ID | Mechanism | Evidence fit | Oracle? | Extra LLM calls? | Genome-safe? |
|---|---|---|---|---|---|
| M1 | **Action–Observation recorder** (state/action/feedback/locations/inventory) | direct — fixes memory gap | no | 0 (logging) | yes — recorder is shared infra; `memory_strategy` still chooses window k |
| M2 | Stagnation detector (diagnostic flag) | matches LOOP_STAGNATION 17/18 | no | 0 | yes if diagnostic-only |
| M3 | Goal-state tracker (evidence flags) | matches incomplete relations | no | 0 | yes |
| M4 | Failure-driven reflection | would need new trigger | no | **+1 on stagnation** | interacts with `reflection_strategy` |

## Selected minimal shared repair: **M1 + M2 + M3 as one diagnostic package**

**Chosen:** `src/diagnostics/shared_repair.py` (ActionObservationRecorder +
StagnationDetector + goal_state_tracker).

**Why not M4 now:** adds LLM calls (cost shift) and conflates with
`reflection_strategy` gene. Defer until M1–M3 are baseline-shared.

**Why not all four:** M4 changes cost distribution; Stage 1 showed cost is
already a gene-sensitive objective — adding calls would bias G1/G2/G3
comparisons unless applied identically and re-baselined.

### Design constraints honored

1. Matches real failure trajectories (object-not-found + loops).
2. Fully offline-testable (`tests/test_shared_repair.py`, 7 PASS).
3. No oracle leakage — `native_success_confirmed` is never auto-set.
4. **Genome semantics preserved:** shared recorder infrastructure ≠ shared
   memory policy. `memory_strategy` still selects how many history lines the
   prompt sees (`none` / `short_term`=1 / `episodic`≤3).
5. Fair for all algorithms when default-on for every arm.
6. Zero extra LLM calls for M1–M3.
7. ObjectiveSpec untouched.
8. Cost distribution unchanged while M1–M3 are logging-only.

## Evidence level

| Claim | Level |
|---|---|
| Recorder captures locations/objects | OFFLINE_TEST_CONFIRMED |
| Stagnation flags repeats | OFFLINE_TEST_CONFIRMED |
| Goal flags track evidence | OFFLINE_TEST_CONFIRMED |
| Improves real DeepSeek success | **UNVERIFIED** (needs A/B) |

## Integration policy (NOT executed)

- Ship as **default-on shared baseline** for all methods after Planner approval.
- Do not enable only for PEEM/PPEC arms.
- Keep DecisionLog fields additive.
- Re-run feasibility block after integration before any evolutionary claim.
