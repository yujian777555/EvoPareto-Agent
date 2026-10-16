# Stage 1.6 Offline Validation

**All three gates PASS. Real API calls before live A/B: 0.**

---

## Gate A — Goal-State Correctness: PASS

Tests: `tests/test_goal_state_evidence.py` (12) + `tests/test_shared_repair.py` (7) = **19 passed**.

| Requirement | Counter-example test |
|---|---|
| Goal text ≠ discovery | `test_goal_text_is_not_discovery` |
| take without feedback ≠ acquired | `test_take_command_without_feedback_is_not_acquired` |
| pickup then release clears hold | `test_successful_pickup_then_release_clears_hold` |
| use lamp unconfirmed ≠ lit | `test_use_lamp_unconfirmed_not_lit` |
| wrong object placement ≠ manipulation | `test_wrong_object_placement_not_manipulation` |
| history alone ≠ found | `test_history_alone_not_found` |
| repeated obs ≠ phantom progress | `test_repeated_observation_no_fantom_progress` |
| native won only from env | `test_native_won_only_from_environment` |
| no oracle fields in module | `test_no_oracle_fields_in_module` |

State machine: `NOT_OBSERVED → OBSERVED → ACQUIRED → RELEASED` / `UNKNOWN`.
Pickup/place/light require **matching environment feedback**, not command names.

## Gate B — Runtime Integration: PASS

Tests: `tests/test_runtime_integration.py` (9 passed).

| Check | Result |
|---|---|
| current prompt has no progress/stagnation block | `test_current_runtime_prompt_matches_legacy_shape` |
| repaired prompt contains Observed Progress + history | `test_repaired_runtime_prompt_contains_verified_block` |
| stagnation warning appears on repeats | `test_repaired_stagnation_warning_appears` |
| no extra LLM calls | `test_repaired_no_extra_llm_calls_vs_current` |
| same mock action sequence both runtimes | `test_current_runtime_actions_identical_with_mock` |
| no expert leakage in prompt | asserted in repaired prompt test |

## Gate C — Native Success Propagation: PASS

Script: `scripts/stage1_6_gate_c.py` (Docker, 0 LLM).
Evidence: `results/stage1_5/gate_c_native_propagation.json`.

| Task | EpisodeRunner success | Negative |
|---:|---|---|
| 0 | **True** (4 scripted steps) | NEG_PASS |
| 10 | **True** | NEG_PASS |
| 20 | **True** | NEG_PASS |

Expert sequences used **only** as offline test policy — not injected into the
real A/B agent.

---

**All gates passed → authorized to run the frozen 12-episode A/B.**
