# Stage 1 DecisionLog Validation

**Scope:** observational logging only. 0 real API calls.  
**Files changed:** `src/runtime/interactive_agent.py`, `src/runtime/episode_runner.py`.  
**Behavior rule:** with the same Mock LLM responses and the same observations,
the action sequence is **bit-identical** before and after logging.

---

## 1. Fields captured per decision

```
episode_id (via episode context), step_index, goal,
observation_preview, admissible_commands (still in trajectory),
raw_llm_response, parsed_action, parse_ok, parse_failure_reason,
used_fallback, reflection_trigger, reflection_response,
executed_action, observation_after (via trajectory),
native_won (via trajectory),
llm_calls, tokens_in, tokens_out, estimated_cost_usd
```

If one environment action used **two** LLM calls (parse failure + reflection),
`llm_calls=2` and both calls' usage is summed on that decision; the
`call_usage_journal` in the episode keeps per-call rows.

**No API keys / Authorization headers are stored** (test asserts banned fields
do not appear).

## 2. Behavior invariance evidence

| Property | Test | Result |
|---|---|---|
| identical action sequence over repeated runs | `test_action_sequence_deterministic_across_runs` | PASS |
| zero extra LLM calls from logging | `test_no_extra_llm_calls_with_logging` | PASS (1 call, not 2) |
| reflection still exactly 2 calls on parse failure | `test_parse_failure_reflection_uses_exactly_two_calls` | PASS |
| fallback still first admissible | `test_fallback_logged_when_all_parses_fail` | PASS |
| MemoryStore items unchanged | `test_memory_content_unchanged_by_logging` | PASS |
| BudgetMeter charges unchanged (1 per LLM call) | `test_budget_charge_unchanged` | PASS |
| episode exports full decision_logs + usage | `test_episode_runner_exports_decision_logs_with_usage` | PASS |
| two-call decision keeps both usages | `test_reflection_decision_log_keeps_both_calls` | PASS |

Decision logic (`_parse_action`, fallback rule, reflection trigger condition,
prompt construction, budget charges) was **not** modified. Only extra fields on
`DecisionLog` and a usage journal in `EpisodeRunner` were added.

## 3. What this enables next run

Distinguish for the first time:

- LLM-chosen repeats vs parser-mapped repeats (`raw_llm_response` vs `parsed_action`)
- fallback-driven repeats (`used_fallback`)
- reflection frequency and its trigger (`reflection_trigger`)
- per-step token/cost attribution

## 4. Explicitly NOT added (forbidden this round)

Anti-loop suppression · new reflection triggers · new memory controller ·
new planner · action reranking · prompt-engineering changes.
