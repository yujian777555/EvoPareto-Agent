# AFlow Algorithm Code Map

Source: `external/AFlow/scripts/` @ `3f45721…`

## Search loop (`optimizer.py::Optimizer._optimize_graph`)

```
for round in max_rounds:
  top_rounds = data_utils.get_top_rounds(sample)      # unique rounds by score
  parent    = data_utils.select_round(top_rounds)     # mixed softmax+uniform
  prompt, graph = graph_utils.read_graph_files(parent)
  experience    = experience_utils.format_experience(...)
  response      = optimize_llm(GraphOptimize prompt)  # LLM edits code+prompt
  check_modification(experience, response.modification)  # exact-string dedup
  write graph.py + prompt.py for round+1
  score = evaluation_utils.evaluate_graph(validation_rounds)
  experience_utils.update_experience(...)             # succeed = score>before
  convergence_utils.check_convergence(top_k=3)
```

## Paper vs code

| Paper claim | Code reality | Note |
|---|---|---|
| MCTS | top-k mixed-distribution sampling + LLM edit | **PAPER_CODE_DIVERGENCE** (simplification) |
| tree experience | per-father-node success/failure modification lists | text-in-prompt + string dedup |
| backpropagation | none (round scores stored) | no UCT updates |
| operators | Custom, ScEnsemble, Programmer, Review/Revise… | real Python Operator classes |

## Workflow representation

`Workflow` Python class composing `Operator` calls + `prompt.py`. LLM
generates new `graph.py`/`prompt.py` per round → optimizes **code + prompts
together**, not pure DAG topology.

## Experience quirk (candidate limitation)

`format_experience` emits **"Absolutely prohibit {modification}" for both
successes and failures** — successful edits are also blacklisted from exact
repeats. `check_modification` dedups on exact string equality only.
