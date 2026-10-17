# Evidence Taxonomy (Task D)

| Flag | Meaning |
|---|---|
| XML_VALID | modification/graph/prompt tags all present |
| GRAPH_SYNTAX_VALID | graph compiles and defines `class Workflow` |
| PROMPT_CONTRACT_VALID | prompt serialises to a module with `INSTRUCTION` |
| BUNDLE_LOAD_VALID | both modules compile and can be imported |
| WORKFLOW_EXECUTABLE | Docker child rc=0 |
| IPC_REACHED | >=1 mailbox model request |
| TASK_CORRECT | host scorer exact-match (host-only gold) |

## Live Level 3 (original, preserved)

{
  "XML_VALID": true,
  "GRAPH_SYNTAX_VALID": true,
  "PROMPT_CONTRACT_VALID": false,
  "BUNDLE_LOAD_VALID": false,
  "WORKFLOW_EXECUTABLE": false,
  "IPC_REACHED": false,
  "TASK_CORRECT": false
}

## L3-R1 replay

{
  "XML_VALID": true,
  "GRAPH_SYNTAX_VALID": true,
  "PROMPT_CONTRACT_VALID": true,
  "BUNDLE_LOAD_VALID": true,
  "WORKFLOW_EXECUTABLE": true,
  "IPC_REACHED": true,
  "TASK_CORRECT": false
}

## Thinking disabled

{
  "request_sent_with": "{\"thinking\": {\"type\": \"disabled\"}}",
  "independently_verifiable": false,
  "claim": "request-side only; cannot independently verify the served model's reasoning mode",
  "model_version_observed": "deepseek-flash",
  "model_version_independently_verified": false,
  "note": "API reported model id only; underlying serving version not independently confirmed"
}

**XML structure completeness is not claimed as full candidate validity.**
The original Level 3 failure report under `results/level3_live_calibration/`
is **not overwritten**.
