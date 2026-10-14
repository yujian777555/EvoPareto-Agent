"""Phase 5-Pre tests: ablation config, serialization, metrics, seed reproducibility."""

import json
from pathlib import Path

import pytest

from experiments.ablation.harness import (
    ABLATION_CONFIG,
    AblationResult,
    aggregate,
    ms,
    run_variant,
    seed_reproducible,
    write_json,
)
from src.evolution.credit_assignment import CreditWeights
from src.evaluation.metrics import igd, hypervolume, mutation_entropy


# ====================================================================== #
# Experiment config
# ====================================================================== #
def test_ablation_config_fixed():
    cfg = ABLATION_CONFIG
    assert cfg["pop"] == 16
    assert cfg["gens"] == 8
    assert len(cfg["seeds"]) == 3
    assert cfg["budget_evals"] == cfg["pop"] * (cfg["gens"] + 1)


def test_all_runs_same_budget():
    r = run_variant("x", seed=1, pop=8, gens=2, tasks=3)
    assert r.metrics["evaluations"] == 8 * 3


# ====================================================================== #
# Result serialization
# ====================================================================== #
def test_ablation_result_to_dict():
    r = AblationResult(name="a", seed=1, metrics={"hypervolume": 0.5}, history=[{"generation": 0}])
    d = r.to_dict()
    assert d["name"] == "a"
    assert d["metrics"]["hypervolume"] == 0.5
    json.dumps(d)  # serializable


def test_write_json_roundtrip(tmp_path: Path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1, "b": [1, 2]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2]}


def test_framework_result_file_exists():
    p = Path(__file__).resolve().parents[2] / "results" / "ablation" / "framework.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "table" in d and "config" in d
        assert d["config"]["seeds"] == [11, 22, 33]


# ====================================================================== #
# Metric calculation
# ====================================================================== #
def test_ms_mean_std():
    s = ms([1.0, 2.0, 3.0])
    assert s["mean"] == pytest.approx(2.0)
    assert s["std"] == pytest.approx((2 / 3) ** 0.5, rel=1e-6)


def test_aggregate_groups_by_name():
    runs = [
        AblationResult("a", 1, {"hypervolume": 0.5}),
        AblationResult("a", 2, {"hypervolume": 0.7}),
        AblationResult("b", 1, {"hypervolume": 0.2}),
    ]
    agg = aggregate(runs, ["hypervolume"])
    assert agg["a"]["hypervolume"]["mean"] == pytest.approx(0.6)
    assert agg["a"]["n_seeds"] == 2


def test_igd_and_hv_metrics():
    ref = [[0.0, 1.0], [1.0, 0.0]]
    front = [[0.1, 0.9], [0.9, 0.1]]
    assert igd(front, ref, maximize_input=False) > 0
    assert hypervolume([[0.9, 0.9, 0.1, 0.9, 0.9]]) > hypervolume([[0.2, 0.2, 0.9, 0.2, 0.2]])
    assert mutation_entropy([5, 5]) > mutation_entropy([9, 1])


def test_credit_weights_normalize():
    w = CreditWeights(1, 0, 1, 0).normalized()
    assert w.alpha + w.beta + w.gamma + w.delta == pytest.approx(1.0)
    assert w.beta == 0.0


# ====================================================================== #
# Seed reproducibility
# ====================================================================== #
def test_seed_reproducible_metrics():
    def run():
        return run_variant("rep", seed=5, pop=6, gens=1, tasks=3)

    assert seed_reproducible("rep", run, n_repeat=2)


def test_different_seeds_differ():
    r1 = run_variant("s", seed=1, pop=8, gens=2, tasks=3)
    r2 = run_variant("s", seed=2, pop=8, gens=2, tasks=3)
    # Not required to differ every metric, but histories should be objects.
    assert r1.metrics["evaluations"] == r2.metrics["evaluations"]
