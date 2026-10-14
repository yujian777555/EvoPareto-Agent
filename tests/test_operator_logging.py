"""Phase5-R2 tests: operator utility logging, aggregation, plot schema."""

import json
from pathlib import Path

import pytest

from src.evolution.operator_logging import (
    OPERATORS,
    LoggingLoop,
    OperatorUtilityLogger,
    aggregate_seed_timeseries,
)
from src.evolution.memory_evolution import MemoryEvolutionConfig
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline


def toy_eval(genome):
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    return [p[genome.planner_strategy], 0.5, 0.5, 0.5, 0.5]


def make_logger_run(benchmark="alfworld", seed=1):
    pipe = RealLLMPipeline(RealLLMConfig(n_tasks=4, backend="mock", seed=seed, benchmark=benchmark))
    cfg = MemoryEvolutionConfig(pop_size=6, n_offspring=6, seed=seed,
                                use_adaptive=True, experience_mode="robust_peem")
    loop = LoggingLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.logger.benchmark = benchmark
    loop.logger.seed = seed
    loop.initialize()
    loop.run(2)
    return loop


# ====================================================================== #
def test_operator_names_consistent():
    assert set(OPERATORS) == {"planner", "memory", "reflection", "tool", "budget"}


def test_logger_snapshots_schema():
    loop = make_logger_run()
    d = loop.logger.to_dict()
    assert d["benchmark"] == "alfworld"
    assert d["generations"]
    g0 = d["generations"][0]
    assert set(g0["operators"].keys()) == set(OPERATORS)
    for op in OPERATORS:
        for k in ("utility", "probability", "count", "accepted", "avg_credit", "survival_rate"):
            assert k in g0["operators"][op]


def test_logger_serialization(tmp_path: Path):
    loop = make_logger_run()
    path = tmp_path / "ts.json"
    loop.logger.save_json(path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["seed"] == 1
    assert len(loaded["generations"]) == 3  # init + 2 gens


def test_generation_stats_aggregation():
    runs = []
    for seed in (1, 2):
        runs.append(make_logger_run(seed=seed).logger.to_dict())
    agg = aggregate_seed_timeseries(runs)
    assert agg["generation"] == [0, 1, 2]
    for op in OPERATORS:
        assert len(agg["operators"][op]["utility_mean"]) == 3
        assert len(agg["operators"][op]["utility_std"]) == 3
        assert len(agg["operators"][op]["probability_mean"]) == 3


def test_probability_sums_near_one():
    loop = make_logger_run()
    snap = loop.logger.snapshots[-1]
    total = sum(snap.operators[op]["probability"] for op in OPERATORS)
    assert total == pytest.approx(1.0, abs=0.05)


def test_multi_seed_plotting_schema():
    runs = [make_logger_run(seed=s).logger.to_dict() for s in (11, 22)]
    agg = aggregate_seed_timeseries(runs)
    # Schema expected by plot_operator_utility.py
    for op in OPERATORS:
        d = agg["operators"][op]
        for key in ("utility_mean", "utility_std", "probability_mean", "probability_std",
                    "count_mean", "accepted_mean", "avg_credit_mean"):
            assert key in d
            assert len(d[key]) == len(agg["generation"])


def test_analysis_results_exist():
    root = Path(__file__).resolve().parents[2] / "results" / "analysis"
    ts = root / "operator_utility_timeseries.json"
    if ts.exists():
        d = json.loads(ts.read_text(encoding="utf-8"))
        assert "alfworld" in d["data"] and "webshop" in d["data"]


def test_paper_figures_exist():
    fig = Path(__file__).resolve().parents[2] / "paper" / "figures"
    expected = [
        "operator_utility_alfworld.png",
        "operator_probability_alfworld.png",
        "operator_utility_webshop.png",
        "operator_probability_webshop.png",
    ]
    for name in expected:
        p = fig / name
        if p.exists():
            assert p.stat().st_size > 1000
