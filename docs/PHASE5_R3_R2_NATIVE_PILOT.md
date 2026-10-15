# Phase5-R3-R2 — Native Pilot Log

## Rule policy (connectivity)

- 3 episodes, `valid_unseen`, max_steps=12
- result: 0/3 success (expected; OOD household tasks)
- **evaluation_kind = real_environment**
- file: `results/native_alfworld/smoke/pilot_rule.json`

## DeepSeek `deepseek-flash` + InteractiveAgent

- 2 episodes, max_steps=8
- api_calls: 8 and 10 (real HTTP to DeepSeek)
- success: 0/2 (allowed — acceptance is execution chain)
- trajectory / score / won from **native env**
- file: `results/native_alfworld/pilot/deepseek_ep2.json`

## Evidence chain

```text
reset (real TextWorld obs)
  → InteractiveAgent.select_action (genome behavior + LLM)
  → step(admissible command)
  → new obs / score / won
  → success = won
```

No capability prior. No mock LLM. No synthetic success.
