"""Phase 2.5-R1 tests: rank credit, normalization, delayed credit, temperature."""

import math
import random

import pytest

from src.evolution.adaptive_mutation import AdaptiveMutationController, default_registry
from src.evolution.credit_assignment import (
    CreditWeights,
    RobustCreditBreakdown,
    apply_normalized_mv,
    compute_robust_credit,
    robust_raw_components,
)
from src.evolution.delayed_credit import DelayedCreditBook, new_mutation_id
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop, run_memory_evolution
from src.evolution.normalization import (
    GenerationNormalizer,
    mean_std,
    normalize_batch,
    zscore,
    zscore_clip,
)
from src.evolution.pareto_credit import (
    ParetoContributionEstimator,
    dominance_count,
    rank_bucket_score,
)
from src.evolution.pareto_experience import PEEMConfig, ParetoExperience


def toy_eval(genome):
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    e = {"direct": 0.9, "cot": 0.7, "plan_and_solve": 0.55, "tree_search": 0.35, "reflexion": 0.45}
    c = {"no_tools": 0.1, "conservative": 0.3, "balanced": 0.45, "aggressive": 0.7, "tool_first": 0.85}
    t = (genome.reasoning_budget - 8) / 120.0
    return [
        p[genome.planner_strategy] + 0.05 * t,
        e[genome.planner_strategy] - 0.2 * t,
        c[genome.tool_policy] + 0.3 * t,
        0.5 + 0.3 * p[genome.planner_strategy],
        0.5 + 0.2 * e[genome.planner_strategy],
    ]


# ====================================================================== #
# 1. Pareto contribution estimator
# ====================================================================== #
def test_rank_bucket_scores():
    assert rank_bucket_score(0.0) == 1.0
    assert rank_bucket_score(0.19) == 1.0
    assert rank_bucket_score(0.2) == 0.5
    assert rank_bucket_score(0.5) == 0.5
    assert rank_bucket_score(0.7) == 0.0
    assert rank_bucket_score(1.0) == 0.0


def test_pareto_estimator_batch_ranks():
    est = ParetoContributionEstimator()
    parents = [[0.5] * 5 for _ in range(10)]
    children = []
    for i in range(10):
        # decreasing quality
        children.append([0.1 * (10 - i)] * 2 + [0.1 * i] + [0.1 * (10 - i)] * 2)
    scores = est.score_batch(parents, children, parents)
    assert len(scores) == 10
    assert scores[0] == 1.0  # best child
    assert scores[-1] == 0.0  # worst child
    assert set(scores) <= {0.0, 0.5, 1.0}


def test_pareto_estimator_single():
    est = ParetoContributionEstimator()
    parent = [0.5, 0.5, 0.5, 0.5, 0.5]
    # Strong child: better on max objectives AND cost (lower)
    strong = [0.9, 0.9, 0.1, 0.9, 0.9]
    # Weak child: worse on max objectives AND cost
    weak = [0.1, 0.1, 0.9, 0.1, 0.1]
    assert est.score_one(parent, strong, [[0.2, 0.2, 0.8, 0.2, 0.2]]) == 1.0
    assert est.score_one(parent, weak, [[0.9, 0.9, 0.1, 0.9, 0.9]]) == 0.0


def test_dominance_count():
    # Mixed semantics: [0.6,0.6,0.4,...] dominates [0.5,0.5,0.5,...]
    child = [0.5, 0.5, 0.5, 0.5, 0.5]
    others = [
        [0.6, 0.6, 0.4, 0.6, 0.6],  # dominates child
        [0.4, 0.4, 0.6, 0.4, 0.4],  # dominated by child
        [0.7, 0.7, 0.3, 0.7, 0.7],  # dominates child
    ]
    assert dominance_count(child, others) == 2


# ====================================================================== #
# 2. Normalization
# ====================================================================== #
def test_zscore_basic():
    zs = zscore([1.0, 2.0, 3.0])
    assert zs[1] == pytest.approx(0.0)
    assert zs[0] < 0 < zs[2]


def test_zscore_degenerate_std():
    assert zscore([2.0, 2.0, 2.0]) == [0.0, 0.0, 0.0]


def test_mean_std():
    mu, sd = mean_std([1.0, 3.0])
    assert mu == pytest.approx(2.0)
    assert sd == pytest.approx(1.0)


def test_zscore_clip():
    zs = zscore_clip([0.0, 1.0, 100.0])
    assert all(-3.0 <= z <= 3.0 for z in zs)


def test_generation_normalizer():
    n = GenerationNormalizer()
    n.add("improvement", 1.0)
    n.add("improvement", 3.0)
    n.add("pareto", 0.5)
    n.add("pareto", 0.5)
    n.fit()
    assert n.transform("improvement", 2.0) == pytest.approx(0.0)
    assert n.transform("pareto", 0.5) == 0.0  # degenerate std


def test_normalize_batch():
    rows = [{"a": 1.0}, {"a": 2.0}, {"a": 3.0}]
    out = normalize_batch(rows)
    assert out[1]["a"] == pytest.approx(0.0)


# ====================================================================== #
# 3. Delayed credit
# ====================================================================== #
def test_delayed_register_and_bonus():
    book = DelayedCreditBook(horizon=3)
    mid = new_mutation_id()
    book.register(mid, generation=1, mutation_type="planner", child_objectives=[0.5] * 5)
    assert book.get(mid) is not None
    assert book.delayed_bonus(mid) == 0.0


def test_delayed_future_survival_and_pareto():
    book = DelayedCreditBook(horizon=5)
    mid = new_mutation_id()
    book.register(mid, generation=1, mutation_type="tool", child_objectives=[0.8, 0.8, 0.2, 0.8, 0.8])
    # Population that child dominates many points of
    book.observe_population([[0.2] * 5, [0.3] * 5], generation=2)
    rec = book.get(mid)
    assert rec["future_survival"] >= 1
    assert rec["future_pareto_gain"] >= 1
    assert book.delayed_bonus(mid) > 0
    assert book.total_value(mid) > 0


def test_delayed_horizon_expires():
    book = DelayedCreditBook(horizon=2)
    mid = new_mutation_id()
    book.register(mid, generation=1, mutation_type="budget", child_objectives=[0.5] * 5)
    book.step(generation=4)
    assert book.get(mid)["closed"] is True
    assert book.clear_closed() == 1


def test_delayed_type_aggregates():
    book = DelayedCreditBook()
    for _ in range(3):
        book.register(new_mutation_id(), generation=1, mutation_type="memory", child_objectives=[0.5] * 5)
    agg = book.type_aggregates()
    assert agg["memory"]["n"] == 3


# ====================================================================== #
# 4. Temperature sampling
# ====================================================================== #
def test_softmax_temperature_high_is_flatter():
    exp = ParetoExperience(PEEMConfig(decay=1.0, prior_value=0.5))
    for name in default_registry().names():
        exp._absorb(name, 1.0 if name == "planner" else 0.1, {})
    hot = AdaptiveMutationController(experience=exp, registry=default_registry(), temperature=5.0, use_softmax=True, epsilon=0.0)
    cold = AdaptiveMutationController(experience=exp, registry=default_registry(), temperature=0.1, use_softmax=True, epsilon=0.0)
    dh = hot.probability_distribution()
    dc = cold.probability_distribution()
    assert dc["planner"] > dh["planner"]  # cold sharpens
    assert sum(dh.values()) == pytest.approx(1.0)


def test_temperature_annealing():
    ctrl = AdaptiveMutationController(
        experience=ParetoExperience(),
        registry=default_registry(),
        temperature=1.0,
        temperature_min=0.2,
        temperature_step=0.1,
        use_softmax=True,
    )
    t0 = ctrl.current_temperature()
    for _ in range(10):
        ctrl.select_mutation(random.Random(0))
    t1 = ctrl.current_temperature()
    assert t1 < t0
    assert t1 >= 0.2


def test_temperature_select_deterministic():
    ctrl = AdaptiveMutationController(
        experience=ParetoExperience(),
        registry=default_registry(),
        temperature=0.5,
        use_softmax=True,
    )
    _, n1 = ctrl.mutate(
        __import__("src.agent.genome", fromlist=["AgentGenome"]).AgentGenome.random(random.Random(0)),
        random.Random(3),
        n_mutations=2,
    )
    ctrl2 = AdaptiveMutationController(
        experience=ParetoExperience(),
        registry=default_registry(),
        temperature=0.5,
        use_softmax=True,
    )
    _, n2 = ctrl2.mutate(
        __import__("src.agent.genome", fromlist=["AgentGenome"]).AgentGenome.random(random.Random(0)),
        random.Random(3),
        n_mutations=2,
    )
    assert n1 == n2


def test_softmax_disabled_falls_back():
    ctrl = AdaptiveMutationController(
        experience=ParetoExperience(),
        registry=default_registry(),
        use_softmax=False,
    )
    dist = ctrl.probability_distribution()
    assert abs(sum(dist.values()) - 1.0) < 1e-6


# ====================================================================== #
# 5. Robust credit + long-horizon evolution
# ====================================================================== #
def test_robust_raw_components():
    raw = robust_raw_components([0.5] * 5, [0.7, 0.5, 0.3, 0.5, 0.5], population=[[0.4] * 5], survived=True)
    assert isinstance(raw, RobustCreditBreakdown)
    assert raw.survival_score == 1.0
    assert raw.pareto_score in (0.0, 0.5, 1.0)


def test_robust_mv_uses_z_and_buckets():
    raw = robust_raw_components([0.5] * 5, [0.8, 0.5, 0.2, 0.5, 0.5], population=[[0.1] * 5], survived=True)
    apply_normalized_mv(raw, delayed_bonus=0.1)
    assert raw.mutation_value != 0
    d = raw.to_dict()
    assert "improvement_norm" in d and "pareto_norm" in d


def test_compute_robust_credit():
    br = compute_robust_credit([0.5] * 5, [0.9] * 5, population=[[0.1] * 5], survived=True)
    assert br.mutation_value > 0


def test_robust_mode_long_horizon():
    out = run_memory_evolution(
        toy_eval,
        pop_size=16,
        n_generations=8,
        seed=21,
        experience_mode="robust_peem",
        use_delayed_credit=True,
    )
    hist = out["history"]
    assert len(hist) == 9
    assert hist[-1]["hypervolume"] >= 0
    assert "temperature" in hist[-1]
    assert out["mutation_probs"]
    assert isinstance(out["delayed"], DelayedCreditBook)
    assert len(out["archive"]) > 0


def test_robust_vs_peem_v1_modes():
    r = run_memory_evolution(toy_eval, pop_size=12, n_generations=3, seed=22, experience_mode="robust_peem")
    p = run_memory_evolution(toy_eval, pop_size=12, n_generations=3, seed=22, experience_mode="peem")
    assert r["final_hypervolume"] >= 0 and p["final_hypervolume"] >= 0


def test_noisy_evaluator_robust_mode():
    import random as _r

    def noisy(genome):
        base = toy_eval(genome)
        rng = _r.Random(hash(genome.key()) & 0xFFFF)
        return [min(1.0, max(0.0, v + rng.uniform(-0.05, 0.05))) for v in base]

    out = run_memory_evolution(noisy, pop_size=12, n_generations=4, seed=23, experience_mode="robust_peem")
    assert out["final_hypervolume"] >= 0
    assert len(out["history"]) == 5
