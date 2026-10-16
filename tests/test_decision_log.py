"""DecisionLog observation tests + behavior-invariance checks (offline, no API).

Guarantees:
- logging is purely observational
- action sequences are identical for fixed Mock LLM + fixed observations
- no extra LLM calls are introduced
- memory / parse / fallback / budget semantics are unchanged
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.runtime.episode_runner import EpisodeRunner, parse_llm_return
from src.runtime.interactive_agent import DecisionLog, InteractiveAgent
from src.runtime.behavioral_agent import BudgetMeter, MemoryStore

ROOT = Path(__file__).resolve().parents[1]


class ScriptedLLM:
    """Returns queued responses; records every prompt (call count)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.i = 0

    def __call__(self, prompt):
        self.prompts.append(prompt)
        r = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return r


def _genome(**kw):
    base = dict(
        planner_strategy="cot",
        memory_strategy="short_term",
        reflection_strategy="self_critique",
        tool_policy="balanced",
        reasoning_budget=64,
    )
    base.update(kw)
    return AgentGenome(**base)


# ------------------------------------------------------------------ #
# Behavior invariance: same mock responses -> same action sequence
# ------------------------------------------------------------------ #
def test_action_sequence_deterministic_across_runs():
    g = _genome()
    adm = ["go to bed 1", "go to desk 1", "look", "examine desk 1"]
    obs = "On the desk 1, you see a laptop 3."
    goal = "look at book under the desklamp."
    seqs = []
    call_counts = []
    for _ in range(3):
        llm = ScriptedLLM(["examine desk 1", "look", "go to desk 1"])
        agent = InteractiveAgent(g, llm, horizon=30)
        acts = [agent.select_action(obs, adm, goal=goal) for _ in range(3)]
        seqs.append(acts)
        call_counts.append(len(llm.prompts))
    assert seqs[0] == seqs[1] == seqs[2]
    assert call_counts[0] == call_counts[1] == call_counts[2] == 3
    assert seqs[0] == ["examine desk 1", "look", "go to desk 1"]


def test_no_extra_llm_calls_with_logging():
    g = _genome(reflection_strategy="none")
    llm = ScriptedLLM(["look"])
    agent = InteractiveAgent(g, llm, horizon=10)
    agent.select_action("obs", ["look", "go to desk 1"], goal="g")
    assert len(llm.prompts) == 1  # logging adds zero calls
    assert len(agent.decision_logs) == 1
    assert agent.decision_logs[0].llm_calls == 0  # filled by EpisodeRunner


def test_parse_failure_reflection_uses_exactly_two_calls():
    g = _genome(reflection_strategy="self_critique")
    llm = ScriptedLLM(["not a valid command at all", "look"])
    agent = InteractiveAgent(g, llm, horizon=10)
    act = agent.select_action("obs", ["look", "go to desk 1"], goal="g")
    assert act == "look"
    assert len(llm.prompts) == 2
    dl = agent.decision_logs[0]
    assert dl.parse_ok is True  # second parse succeeded
    assert dl.reflected is True
    assert dl.reflection_trigger == "parse_failure"
    assert dl.raw_response.startswith("not a valid")
    assert "look" in dl.reflection_raw


def test_fallback_logged_when_all_parses_fail():
    g = _genome(reflection_strategy="none")
    llm = ScriptedLLM(["zzz nope"])
    agent = InteractiveAgent(g, llm, horizon=10)
    act = agent.select_action("obs", ["go to bed 1", "look"], goal="g")
    assert act == "go to bed 1"  # first admissible fallback
    dl = agent.decision_logs[0]
    assert dl.used_fallback is True
    assert dl.parse_ok is False
    assert dl.parse_failure_reason == "no_admissible_match"


def test_memory_content_unchanged_by_logging():
    g = _genome(memory_strategy="short_term")
    llm = ScriptedLLM(["look"])
    agent = InteractiveAgent(g, llm, horizon=10)
    agent.select_action("hello world", ["look"], goal="g")
    # MemoryStore.write receives exactly the same item as before logging
    assert agent.memory.items == ["obs:hello world"]
    assert agent.memory.writes == 1


def test_budget_charge_unchanged():
    # 1 parse-successful call charges 1 step; reflection adds 1 more
    g = _genome(reflection_strategy="self_critique")
    llm = ScriptedLLM(["bad", "look"])
    agent = InteractiveAgent(g, llm, horizon=30)
    agent.select_action("o", ["look"], goal="g")
    assert agent.budget.used_steps == 2  # 2 LLM calls, 2 charges — unchanged semantics
    g2 = _genome(reflection_strategy="none")
    llm2 = ScriptedLLM(["look"])
    a2 = InteractiveAgent(g2, llm2, horizon=30)
    a2.select_action("o", ["look"], goal="g")
    assert a2.budget.used_steps == 1


# ------------------------------------------------------------------ #
# EpisodeRunner DecisionLog integration
# ------------------------------------------------------------------ #
def test_episode_runner_exports_decision_logs_with_usage():
    g = _genome(reflection_strategy="none")
    calls = {"n": 0}

    def llm(prompt):
        calls["n"] += 1
        return {
            "text": "look",
            "usage": {"calls": 1, "tokens_in": 10, "tokens_out": 2, "cost": 0.001},
            "model": "deepseek-flash",
        }

    def reset(episode_index=0):
        return ("Your task is to: demo",), {
            "admissible_commands": (["look", "go to desk 1"],),
            "won": (False,),
            "actual_game_id": "/data/json_2.1.1/valid_train/g/t/game.tw-pddl",
            "requested_split": "valid_train",
        }

    def step(actions):
        return ("o2",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}

    runner = EpisodeRunner(g, llm, horizon=5, model="deepseek-flash", experiment_id="dl")
    ep = runner.run(reset, step, episode_id=0, seed=1)
    assert ep["steps"] == 1
    assert calls["n"] == 1
    logs = ep["decision_logs"]
    assert len(logs) == 1
    d = logs[0]
    required = [
        "step_index", "goal", "observation_preview", "raw_llm_response",
        "parsed_action", "parse_ok", "parse_failure_reason", "used_fallback",
        "reflection_trigger", "reflection_response", "executed_action",
        "llm_calls", "tokens_in", "tokens_out", "estimated_cost_usd",
    ]
    for key in required:
        assert key in d, key
    assert d["parsed_action"] == "look"
    assert d["executed_action"] == "look"
    assert d["parse_ok"] is True
    assert d["used_fallback"] is False
    assert d["llm_calls"] == 1
    assert d["tokens_in"] == 10
    assert d["tokens_out"] == 2
    assert d["estimated_cost_usd"] == pytest.approx(0.001)
    # totals consistent
    assert ep["tokens_in"] == 10
    assert ep["cost_usd"] == pytest.approx(0.001)
    assert len(ep["call_usage_journal"]) == 1


def test_reflection_decision_log_keeps_both_calls():
    g = _genome(reflection_strategy="self_critique")

    def llm(prompt):
        if "Previous reply" in prompt or "invalid" in prompt:
            return {"text": "look", "usage": {"calls": 1, "tokens_in": 5, "tokens_out": 1, "cost": 0.0001}}
        return {"text": "gibberish nothing", "usage": {"calls": 1, "tokens_in": 8, "tokens_out": 1, "cost": 0.0002}}

    def reset(episode_index=0):
        return ("Your task is to: demo",), {
            "admissible_commands": (["look"],), "won": (False,),
            "actual_game_id": "/x/game.tw-pddl", "requested_split": "valid_train",
        }

    def step(actions):
        return ("o",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}

    runner = EpisodeRunner(g, llm, horizon=5, model="deepseek-flash", experiment_id="dl2")
    ep = runner.run(reset, step, episode_id=0, seed=1)
    d = ep["decision_logs"][0]
    assert d["reflection_trigger"] == "parse_failure"
    assert d["llm_calls"] == 2
    # both calls' usage attached to this env action
    assert d["tokens_in"] == 5 + 8
    assert d["tokens_out"] == 2
    assert d["estimated_cost_usd"] == pytest.approx(0.0003)
    assert ep["llm_call_count"] == 2


def test_decision_log_has_no_api_key_fields():
    d = DecisionLog(goal="g", observation_preview="o")
    dumped = json.dumps(d.__dict__)
    for banned in ("api_key", "API_KEY", "Authorization", "Bearer", "token_auth"):
        assert banned not in dumped
