# Failure Taxonomy

`FailureEvidence` fields: task_id, genome_id, failure_category,
observed_symptoms, supporting_trace_ids, diagnostic_confidence, uncertainty,
unknown_flag.

Categories: PLANNING_FAILURE · TOOL_SELECTION_FAILURE · VERIFICATION_FAILURE ·
RECOVERY_FAILURE · CONTEXT_FAILURE · OUTPUT_VALIDITY_FAILURE · UNKNOWN.

## Rules

1. `task failed ≠ planning failure`.
2. LLM explanation is a hypothesis, not ground truth.
3. Symptoms are observable; category requires confidence ≥ 0.35 else UNKNOWN.
4. Symptom→category is **many-to-many** (e.g. `wrong_output_passed` ∈
   {VERIFICATION_FAILURE, PLANNING_FAILURE}) — real ambiguity preserved.
5. Policy input = `context_key()` only; injected fault type never enters.

## When attribution is impossible

Low-confidence diagnosis, contradictory symptoms, novel symptom not in
taxonomy, or genome state that produces no distinguishing trace → `UNKNOWN`.
Unknown contexts get **higher exploration** in FCEOL (`EXPLORATION_UNKNOWN`).
