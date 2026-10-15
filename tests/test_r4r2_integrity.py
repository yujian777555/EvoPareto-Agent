"""Phase5-R3-R4-R2 tests: split integrity, trace, usage, budget fail-fast."""

import pytest

from src.agent.genome import AgentGenome
from src.benchmark.split_integrity import (
    SplitIntegrityError,
    data_dir_for,
    manifest_overlap,
    normalize_game_id,
    resolve_split,
    validate_game_in_split,
)
from src.runtime.api_budget import APICallGate, BudgetExceeded
from src.runtime.episode_runner import EpisodeRunner, parse_llm_return


def g(**kw):
    base = dict(planner_strategy="cot", memory_strategy="episodic",
                reflection_strategy="none", tool_policy="balanced",
                reasoning_budget=64)
    base.update(kw)
    return AgentGenome(**base)


# --- split mapping ---
def test_explicit_split_mapping():
    assert resolve_split("valid_train") == ("train", "valid_train")
    assert resolve_split("valid_seen") == ("eval_in_distribution", "valid_seen")
    assert resolve_split("valid_unseen") == ("eval_out_of_distribution", "valid_unseen")


def test_unsupported_split_fails_closed():
    with pytest.raises(SplitIntegrityError):
        resolve_split("test")
    with pytest.raises(SplitIntegrityError):
        resolve_split("eval_out_of_distribution")  # raw mode name not accepted


def test_validate_game_in_split_accepts_train():
    gid = "/data/json_2.1.1/valid_train/look_at_obj-1/trial_x/game.tw-pddl"
    assert validate_game_in_split(gid, "valid_train")


def test_validate_game_rejects_ood_when_train_requested():
    gid = "/data/json_2.1.1/valid_unseen/pick_and_place-2/trial_y/game.tw-pddl"
    with pytest.raises(SplitIntegrityError):
        validate_game_in_split(gid, "valid_train")


def test_data_dir_paths():
    p = data_dir_for("valid_train", "/data").replace("\\", "/")
    assert p.endswith("json_2.1.1/valid_train")
    assert data_dir_for("valid_unseen", "/data").replace("\\", "/").endswith("valid_unseen")


def test_normalize_game_id():
    assert normalize_game_id("a\\b\\c").count("/") >= 0


def test_manifest_overlap():
    assert manifest_overlap(["a", "b"], ["b", "c"]) == ["b"]


# --- parse_llm_return ---
def test_parse_llm_return_shapes():
    assert parse_llm_return("hi") == ("hi", {})
    t, u = parse_llm_return(("hi", {"calls": 2, "tokens_in": 5}))
    assert t == "hi" and u["calls"] == 2
    t2, u2 = parse_llm_return({"text": "x", "usage": {"tokens_out": 3}, "model": "deepseek-flash"})
    assert t2 == "x" and u2["tokens_out"] == 3 and u2["model"] == "deepseek-flash"


# --- full trajectory + success only from won ---
def _env_factory(won_at=None):
    state = {"n": 0}

    def reset(episode_index=0):
        state["n"] = 0
        return ("Your task is to: demo",), {
            "admissible_commands": (["look", "go x"],),
            "won": (False,),
            "requested_split": "valid_train",
            "actual_game_id": f"/data/json_2.1.1/valid_train/g{episode_index}/t/game.tw-pddl",
        }

    def step(actions):
        state["n"] += 1
        won = won_at is not None and state["n"] >= won_at
        return (f"obs{state['n']}",), (1.0 if won else 0.0,), (won or state["n"] >= 5,), {
            "won": (won,), "admissible_commands": (["look", "go x"],)
        }

    return reset, step


def test_full_trajectory_fields():
    r = EpisodeRunner(g(), lambda p: {"text": "look", "usage": {"calls": 1, "tokens_in": 10, "tokens_out": 1, "cost": 0.001}, "model": "deepseek-flash"}, horizon=3)
    out = r.run(*_env_factory(won_at=2)[:2], episode_id=0)
    assert out["success"] is True
    assert len(out["trajectory"]) == 2
    step = out["trajectory"][0]
    for k in ("step", "observation_before", "admissible_commands", "action",
              "observation_after", "score", "won", "done", "llm_call_count"):
        assert k in step
    assert out["game_id"].endswith("game.tw-pddl")
    assert out["tokens_in"] >= 10  # 2 decisions × 10
    assert out["model"] == "deepseek-flash"


def test_success_only_from_won():
    r = EpisodeRunner(g(), lambda p: "look", horizon=3)
    out = r.run(*_env_factory(won_at=None)[:2], episode_id=0)
    assert out["success"] is False
    assert out["termination_reason"] in ("max_steps", "env_done", "won")


# --- API accounting ---
class _Resp:
    def __init__(self):
        self.text = "OK"
        self.tokens_prompt = 11
        self.tokens_completion = 2
        self.cost = 0.0003
        self.model = "deepseek-flash"


def test_global_gate_shared_across_horizons():
    def backend(prompt, budget=32, **k):
        return _Resp()

    gate = APICallGate(backend, max_calls=5, max_cost_usd=1.0)
    for _ in range(3):
        gate.generate("a")  # H10
    for _ in range(2):
        gate.generate("b")  # H20
    with pytest.raises(BudgetExceeded):
        gate.generate("c")  # H30 shares cap
    assert gate.ledger.requests_ok == 5


def test_http_402_fail_fast_no_retry():
    n = {"c": 0}

    def backend(prompt, budget=32, **k):
        n["c"] += 1
        raise RuntimeError("LLM request failed status=402 Payment Required")

    gate = APICallGate(backend, max_calls=10, max_cost_usd=1.0, max_retries=3)
    with pytest.raises(RuntimeError, match="BLOCKED_BILLING"):
        gate.generate("x")
    assert n["c"] == 1  # fail-fast: no retry ladder on 402


def test_usage_propagates_to_episode():
    r = EpisodeRunner(g(), lambda p: {"text": "look", "usage": {"calls": 1, "tokens_in": 7, "tokens_out": 3, "cost": 0.01}}, horizon=2)
    out = r.run(*_env_factory()[:2], episode_id=0)
    assert out["tokens_in"] >= 7
    assert out["tokens_out"] >= 3
    assert out["cost_usd"] >= 0.01
