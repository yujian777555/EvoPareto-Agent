# Phase 1 — Agent Runtime & Evaluation Foundation

**Status:** complete (built on frozen Phase 0 `3dd75be`)  
**Goal:** AgentGenome is a real evolutionary individual whose fitness comes from a
task-run evaluation loop — not from a hand-written toy formula alone.

## Architecture

```text
AgentGenome
    ↓  AgentBuilder.build()
Agent (planner/memory/reflection/tool/budget + optional LLM backend)
    ↓  AgentRunner / agent.run_task(task)
TaskResult(s)
    ↓  Benchmark.evaluate(agent)  ->  EpisodeResult
    ↓  ObjectiveEvaluator.from_episode()
[performance, efficiency, cost, robustness, autonomy]
    ↓  Population + self-built NSGA-III (Phase 0, unchanged)
Next-generation agents
```

| Module | Role |
|--------|------|
| `src/runtime/task.py` | `TaskSpec` / `TaskSuite` |
| `src/runtime/result.py` | `TaskResult` / `EpisodeResult` |
| `src/runtime/agent_builder.py` | `AgentBuilder` + `Agent` + `LLMBackend` protocol |
| `src/runtime/agent_runner.py` | `agent.run(task)` unified runner |
| `src/runtime/pipeline.py` | `Genome → objectives` + `run_agent_evolution` |
| `src/benchmark/base.py` | `Benchmark` ABC (`evaluate(agent)`) |
| `src/benchmark/mock_benchmark.py` | deterministic mock tasks |
| `src/evaluation/objective_evaluator.py` | `TaskResult → objective vector` |

## Interfaces

### Agent

```python
agent.planner_strategy
agent.memory_strategy
agent.reflection_strategy
agent.tool_policy
agent.reasoning_budget
agent.run_task(task, seed=...) -> TaskResult
```

### Benchmark

```python
class Benchmark:
    def evaluate(self, agent) -> EpisodeResult: ...
    @property
    def n_tasks(self) -> int: ...
```

### TaskResult

`success`, `steps`, `tokens`, `latency`, `cost`, `metadata`

### Objective vector (paper semantics)

| name | direction |
|------|-----------|
| performance | maximize |
| efficiency | maximize |
| cost | **minimize** |
| robustness | maximize |
| autonomy | maximize |

`ObjectiveEvaluator.to_minimization` reuses Phase 0 mixed-direction conversion.

## Future LLM integration

`Agent.llm: Optional[LLMBackend]` with:

```python
class LLMBackend(Protocol):
    def complete(self, prompt: str, *, budget: int) -> str: ...
```

- Phase 1 default `run_task` is a **deterministic behavioral model** (no API).
- GPT / DeepSeek plug in by implementing `LLMBackend` and passing `AgentBuilder(llm=...)`.
- Genome, Population, NSGA-III, and objective schema stay unchanged.

## Demo

```bash
python experiments/run_agent_evolution_demo.py
```

Writes `results/agent_population_history.json`, `agent_pareto_front.json`,
`agent_evolution_summary.json`.

## Tests

```bash
python -m pytest -q
```

Covers: Genome→Agent, runtime execution, benchmark adapter, objective vector
correctness, end-to-end evolution pipeline (70 passed at Phase 1 freeze).

## Non-goals (this phase)

- No commercial API calls
- No large benchmark suite
- No RL
- NSGA-III not modified
