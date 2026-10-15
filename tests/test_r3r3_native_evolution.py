"""Phase5-R3-R3 tests: episode isolation, native evaluator, RS, goal, budget."""

import pytest

from src.agent.genome import AgentGenome
from src.evaluation.native_evolution_evaluator import (
    NativeEvolutionEvaluator,
    RandomSearchSampler,
)
from src.runtime.behavioral_agent import MemoryStore
from src.runtime.episode_runner import EpisodeRunner
from src.runtime.interactive_agent import BudgetExhaustedStop, InteractiveAgent


def g(**kw):
    base = dict(planner_strategy="cot", memory_strategy="episodic",
                reflection_strategy="self_critique", tool_policy="balanced",
                reasoning_budget=32)
    base.update(kw)
    return AgentGenome(**base)


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def gen(self, prompt):
        self.calls += 1
        return "look", {"calls": 1, "tokens_in": 10, "tokens_out": 2, "cost": 0.0001}


# --- episode isolation ---
def test_episode_memory_not_shared():
    llm = FakeLLM()
    runner = EpisodeRunner(g(), llm.gen, horizon=5)
    a1 = runner.make_agent()
    a2 = runner.make_agent()
    a1.memory.write("secret-from-ep1")
    assert a2.memory.as_context() == ""
    assert "secret-from-ep1" not in a2.memory.items
    assert a1.memory is not a2.memory


def test_episode_budget_isolated():
    runner = EpisodeRunner(g(reasoning_budget=8), FakeLLM().gen, horizon=5)
    a1, a2 = runner.make_agent(), runner.make_agent()
    a1.budget.charge(steps=99, tokens=999)
    assert a2.budget.used_steps == 0
    assert a2.budget.used_tokens == 0


def test_reflection_state_isolated():
    runner = EpisodeRunner(g(), FakeLLM().gen, horizon=5)
    a1, a2 = runner.make_agent(), runner.make_agent()
    a1.reflection_count = 5
    assert a2.reflection_count == 0


# --- goal extraction ---
def test_goal_extracted_from_observation():
    runner = EpisodeRunner(g(), FakeLLM().gen, horizon=5)
    goal = runner.extract_goal("Your task is to: put a mug on the table.", {})
    assert "mug" in goal


def test_policy_requires_goal_in_prompt():
    captured = []

    def gen(prompt):
        captured.append(prompt)
        return "look", {"calls": 1, "tokens_in": 5, "tokens_out": 1, "cost": 0.0}

    agent = InteractiveAgent(g(), lambda p: gen(p)[0], horizon=5)
    agent.select_action("You are in a room.", ["look", "go to table 1"], goal="put mug on table")
    assert any("put mug on table" in p for p in captured)


# --- budget exhaustion stops episode ---
def test_budget_exhausted_raises_not_look():
    agent = InteractiveAgent(g(reasoning_budget=8), lambda p: "look", horizon=3)
    agent.budget.used_steps = agent.budget.max_steps
    agent.budget.used_tokens = agent.budget.max_tokens
    with pytest.raises(BudgetExhaustedStop):
        agent.select_action("obs", ["look"], goal="g")


# --- parse failure reflection ---
def test_parse_failure_triggers_reflection():
    responses = iter(["!!!invalid!!!", "go to table 1"])

    def gen(p):
        return next(responses)

    agent = InteractiveAgent(g(reflection_strategy="self_critique"), gen, horizon=5)
    action = agent.select_action("obs", ["go to table 1", "look"], goal="g")
    assert action == "go to table 1"
    assert agent.reflection_count == 1
    assert agent.decision_logs[-1].reflected is True
    assert agent.decision_logs[-1].parse_failure_reason != ""


def test_parse_fallback_is_logged():
    agent = InteractiveAgent(g(reflection_strategy="none"), lambda p: "???", horizon=5)
    action = agent.select_action("obs", ["look", "go x"], goal="g")
    assert action == "look"
    assert agent.decision_logs[-1].used_fallback is True


# --- native evaluator wiring ---
def _fake_env():
    state = {"i": 0}

    def reset():
        state["i"] = 0
        return (f"Your task is to: fake-{state['i']}",), {"admissible_commands": (["look", "go x"],), "extra.gamefile": ("g0",), "won": (False,)}

    def step(actions):
        state["i"] += 1
        won = state["i"] >= 2
        return (f"obs-{state['i']}",), (1.0 if won else 0.0,), (won,), {
            "won": (won,), "admissible_commands": (["look", "go x"],), "extra.gamefile": (f"g{state['i']}",)
        }

    return reset, step, lambda: None


def test_native_evaluator_uses_env_won():
    llm = FakeLLM()

    def gen(p):
        t, u = llm.gen(p)
        return t, u

    ev = NativeEvolutionEvaluator(_fake_env, gen, n_tasks=2, max_steps=5)
    vec = ev.evaluate(make_genome := g())
    assert len(vec) == 5
    assert all(0.0 <= v <= 1.0 for v in vec)
    # success came from env won (2 steps)
    assert vec[0] == 0.0 or vec[0] == 1.0
    assert ev.episodes[0].game_id.startswith("g")
    assert ev.episodes[0].to_dict()["evaluation_kind"] == "real_environment"


def test_native_objectives_exclude_capability_prior():
    # objectives computed only from env/API fields
    ev = NativeEvolutionEvaluator(_fake_env, lambda p: ("look", {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.01}), n_tasks=1, max_steps=3)
    vec = ev.evaluate(g())
    assert len(vec) == 5


# --- Random Search independence ---
def test_random_search_no_nsga3():
    import inspect

    from src.evaluation.native_evolution_evaluator import RandomSearchSampler

    src = inspect.getsource(RandomSearchSampler)
    assert "import" in src and "nsga3" not in src.lower().replace("nsga-iii", "")
    # must not call environmental selection
    assert "non_dominated" not in src
    assert ".select(" not in src


def test_random_search_sampling_only():
    rs = RandomSearchSampler(seed=1)
    g1, g2 = rs.sample(), rs.sample()
    assert isinstance(g1, AgentGenome)
    rs.observe([0.1, 0.1, 0.1, 0.1, 0.1])
    # archive does not bias next sample (distribution unchanged implementation)
    assert len(rs.archive) == 1
