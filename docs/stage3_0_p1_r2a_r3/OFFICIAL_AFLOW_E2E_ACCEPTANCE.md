# Official AFlow E2E Acceptance (Task E)

Run id `r3-final-closure` — every flag below is from THIS run.

| Gate | Value |
|---|---|
| OFFICIAL_OPTIMIZER_EXECUTED | True |
| OFFICIAL_PARENT_SELECTION_OBSERVED | True |
| PROVIDER_HTTP_RESPONSE_USED | True |
| STRUCTURED_MUTATION_VALIDATED | True |
| CANDIDATE_GRAPH_SHA_MATCH | True |
| OFFICIAL_EVALUATOR_CALLED | True |
| OFFICIAL_EVALUATOR_CHILD_EXECUTION_OK | True |
| MODEL_IPC_USED | True |
| HOST_GOLD_SCORING_EXECUTED | True |
| EXPERIENCE_WRITTEN_BY_OFFICIAL_UTILS | True |
| RESULTS_WRITTEN_BY_OFFICIAL_UTILS | True |
| ALL_REQUESTS_BUDGET_GATED | True |

## Candidate linkage

```
parent_id -> candidate_id -> graph_sha256 -> prompt_sha256
  -> docker_execution -> task_id -> raw_output
  -> predicted_answer -> gold_answer (host only)
  -> correctness -> experience_record
```

- OPTIMIZER_CANDIDATE_SHA = `d4c8ac1f33dcf4ab757f7c755117fa81aed50dc35809c345b698bba93e3bb7ce`
- evaluator graph SHAs = `['ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e', 'd4c8ac1f33dcf4ab757f7c755117fa81aed50dc35809c345b698bba93e3bb7ce']`
- experience = `workspace/GSM8K/workflows/round_2/experience.json` fields=['after', 'before', 'father node', 'modification', 'succeed']
- results = `workspace/GSM8K/workflows/results.json` n=2

## Gold isolation

CONTAINER_TASK_KEYS = `['task_id','question']`
GOLD_LEAKAGE = False
Mock answers are gold-blind (derived from question text). Wrong answers stay in
the denominator. **Execution success + wrong math is a valid observation.**
