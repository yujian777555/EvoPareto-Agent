"""Gate B/C: runtime integration + native success propagation (offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.runtime.episode_runner import EpisodeRunner
from src.runtime.interactive_agent import InteractiveAgent


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.i = 0

    def __call__(self, prompt):
        self.prompts.append(prompt)
        r = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return r


def g1():
    return AgentGenome("cot", "short_term", "self_critique", "balanced", 64)


# ---------------- Gate B: current unchanged, repaired changes prompt ----------------
def test_current_runtime_prompt_matches_legacy_shape():
    llm = ScriptedLLM(["look"])
    a = InteractiveAgent(g1(), llm, horizon=30, runtime_variant="current")
    a.select_action("You see a desk 1.", ["look", "go to desk 1"], goal="do a thing")
    p = llm.prompts[0]
    assert "Observed Progress:" not in p
    assert "Stagnation Warning" not in p
    assert "Task Goal: do a thing" in p
    assert "Admissible commands:" in p


def test_repaired_runtime_prompt_contains_verified_block():
    llm = ScriptedLLM(["go to desk 1", "take book 2 from desk 1", "look"])
    a = InteractiveAgent(g1(), llm, horizon=30, runtime_variant="shared_repaired")
    a._task_type = "look_at_obj_in_light"
    a.select_action("Your task is to: look at book under the desklamp. You are in a room.",
                    ["go to desk 1", "look"], goal="look at book under the desklamp.")
    # after first action, observe feedback
    a.observe("go to desk 1", "room", "You arrive at desk 1. On the desk 1, you see a book 2.")
    a.select_action("You arrive at desk 1. On the desk 1, you see a book 2.",
                    ["take book 2 from desk 1", "look"], goal="look at book under the desklamp.")
    p2 = llm.prompts[1]
    assert "Observed Progress:" in p2
    assert "target object" in p2
    assert "Recent Actions and Feedback:" in p2
    assert "go to desk 1" in p2
    # no expert leakage
    assert "traj_data" not in p2
    assert "high_pddl" not in p2
    assert len(llm.prompts) == 2  # no extra LLM calls


def test_repaired_stagnation_warning_appears():
    llm = ScriptedLLM(["examine desk 1"] * 6)
    a = InteractiveAgent(g1(), llm, horizon=30, runtime_variant="shared_repaired")
    obs = "On the desk 1, you see a pen 1."
    for i in range(4):
        a.select_action(obs, ["examine desk 1", "look"], goal="look at book under the desklamp.")
        a.observe("examine desk 1", obs, obs)
    last = llm.prompts[-1]
    assert "Stagnation Warning" in last
    assert len(llm.prompts) == 4


def test_repaired_no_extra_llm_calls_vs_current():
    def run(variant):
        llm = ScriptedLLM(["look"])
        a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant=variant)
        a.select_action("o", ["look"], goal="g")
        a.observe("look", "o", "o2")
        a.select_action("o2", ["look"], goal="g")
        return len(llm.prompts)

    assert run("current") == run("shared_repaired") == 2


def test_current_runtime_actions_identical_with_mock():
    def acts(variant):
        llm = ScriptedLLM(["look", "go to desk 1", "examine desk 1"])
        a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant=variant)
        out = []
        for i in range(3):
            out.append(a.select_action(f"obs{i}", ["look", "go to desk 1", "examine desk 1"], goal="g"))
            a.observe(out[-1], f"obs{i}", f"obs{i+1}")
        return out

    assert acts("current") == acts("shared_repaired") == ["look", "go to desk 1", "examine desk 1"]


# ---------------- Gate C: native success propagation ----------------
def test_episode_runner_propagates_native_won():
    """Scripted legal actions → env sets won → EpisodeRunner success=True."""

    def llm(prompt):
        return {"text": "look", "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0}}

    state = {"n": 0}

    def reset(episode_index=0):
        state["n"] = 0
        return ("Your task is to: demo",), {
            "admissible_commands": (["look", "win_cmd"],), "won": (False,),
            "actual_game_id": "/x/game.tw-pddl", "requested_split": "valid_train",
        }

    def step(actions):
        state["n"] += 1
        won = actions[0] == "win_cmd"
        return ("o",), (1.0 if won else 0.0,), (True,), {"won": (won,), "admissible_commands": (["look"],)}

    # force LLM to emit win_cmd
    llm2 = lambda p: {"text": "win_cmd", "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0}}
    runner = EpisodeRunner(g1(), llm2, horizon=5, experiment_id="gatec",
                           runtime_variant="current")
    ep = runner.run(reset, step, episode_id=0, seed=1)
    assert ep["success"] is True


def test_non_completing_actions_no_false_success():
    def llm(prompt):
        return {"text": "look", "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0}}

    def reset(episode_index=0):
        return ("t",), {"admissible_commands": (["look"],), "won": (False,),
                        "actual_game_id": "/x/game.tw-pddl", "requested_split": "valid_train"}

    def step(actions):
        return ("o",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}

    ep = EpisodeRunner(g1(), llm, horizon=5, experiment_id="neg").run(reset, step, episode_id=0, seed=1)
    assert ep["success"] is False


@pytest.mark.parametrize("variant", ["current", "shared_repaired"])
def test_both_variants_run(variant):
    llm = ScriptedLLM(["look"])

    def llmd(p):
        return {"text": "look", "usage": {"calls": 1, "tokens_in": 2, "tokens_out": 1, "cost": 0.0001}}

    def reset(episode_index=0):
        return ("t",), {"admissible_commands": (["look"],), "won": (False,),
                        "actual_game_id": "/x/game.tw-pddl", "requested_split": "valid_train"}

    def step(actions):
        return ("o",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}

    ep = EpisodeRunner(g1(), llmd, horizon=3, experiment_id=variant,
                       runtime_variant=variant).run(reset, step, episode_id=0, seed=1)
    assert ep["runtime_variant"] == variant
    assert ep["steps"] >= 1
