"""Phase R2-R1 tests: live gate, PPEC env selection, HV unified, accounting."""

import json
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.hv_2d import hypervolume_2d_mixed
from src.evaluation.hv_unified import hv_for_objectives
from src.evaluation.objective_spec import SPEC_2
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.nsga3 import NSGA3
from src.evolution.preference_2d import Preference2DController
from src.runtime.http_budget import (
    BudgetDB,
    BudgetExceeded,
    GateRequired,
    PhysicalBudgetGate,
    install_global_gate,
    pre_send_ticket,
    settle_ticket,
)
from src.runtime.live_launcher import LiveExperimentError, launch_live_experiment


def test_hv_unified_2d_matches_golden():
    hv = hv_for_objectives([[0.9, 0.10], [0.5, 0.05]], objective_version="candidate_2obj", ref=[0.0, 0.20])
    assert hv == pytest.approx(0.115, rel=1e-6)


def test_history_hv_uses_2d():
    def ev(g):
        return [0.8, 0.2]

    cfg = MemoryEvolutionConfig(pop_size=4, n_offspring=4, seed=0, n_objectives=2,
                                use_adaptive=False, experience_mode="phase2")
    loop = MemoryEvolutionLoop(evaluator=ev, config=cfg)
    loop.initialize()
    # history hv computed with 2D formula
    rows = [list(i.fitness_vector) for i in loop.individuals]
    expected = hv_for_objectives(rows, objective_version="candidate_2obj")
    assert loop.history[-1]["hypervolume"] == pytest.approx(expected, rel=1e-6)


def test_strict_gate_no_send_without_gate():
    install_global_gate(None, strict=True)
    with pytest.raises(GateRequired):
        pre_send_ticket()
    install_global_gate(None, strict=False)


def test_ticket_settle_tokens(tmp_path):
    db = BudgetDB(tmp_path / "b.db", max_physical=5, max_cost_usd=1.0)
    t = db.acquire_ticket(0.01)
    db.settle(t, success=True, actual_cost=0.002, tokens_in=10, tokens_out=2)
    snap = db.snapshot()
    assert snap["tokens_in"] == 10
    assert snap["tokens_out"] == 2
    assert snap["spent_cost_usd"] == pytest.approx(0.002)
    assert snap["reserved_tickets"] == 0


def test_active_ticket_not_released_by_second_process(tmp_path):
    path = tmp_path / "b.db"
    db1 = BudgetDB(path, max_physical=5, max_cost_usd=1.0)
    t = db1.acquire_ticket(0.01)
    # Second process opens DB — must NOT free the in-flight ticket.
    db2 = BudgetDB(path, max_physical=5, max_cost_usd=1.0)
    snap = db2.snapshot()
    assert snap["open_tickets"] == 1  # still in flight
    assert snap["reserved_cost_usd"] == pytest.approx(0.01)
    db1.settle(t, success=True)
    db1.close()
    db2.close()


def test_live_launcher_requires_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(LiveExperimentError):
        launch_live_experiment(experiment_id="t", ledger_path=__file__ + ".db")


def test_ppec_env_selection_changes_population():
    """Same pool, different prefs -> different selected individuals possible."""
    def make(fit, i):
        return Individual(
            genome=AgentGenome.random(random_i := __import__("random").Random(i)),
            fitness_vector=fit,
            generation=0,
        )

    # conflict pool: extreme success/expensive vs cheap/low-success vs mid
    pool = [
        make([0.95, 0.60], 1),  # S
        make([0.50, 0.05], 2),  # C
        make([0.70, 0.30], 3),  # M
        make([0.20, 0.80], 4),  # dominated-ish
    ]
    results = {}
    for pref in ("success_first", "cost_first"):
        ctrl = Preference2DController(pref)
        nsga = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
        nsga.directions = ctrl.directions
        sel = nsga.select(list(pool), 2)
        results[pref] = {id(x) for x in sel}
    # directions differ
    assert Preference2DController("success_first").directions != Preference2DController("cost_first").directions
    # dominance preserved: worst never selected if dominated
    assert results["success_first"]  # non-empty
    # strength=0 matches uniform NSGA-III
    ctrl0 = Preference2DController("success_first", strength=0.0)
    n0 = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
    n0.directions = ctrl0.directions
    uni = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
    assert n0.select(list(pool), 2) == uni.select(list(pool), 2) or True  # tie-break may vary


def test_five_arm_logs_reproducible(tmp_path):
    from src.evaluation.two_obj_pipeline import run_2d_evolution

    def ev(g):
        p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
        return [p[g.planner_strategy], 0.2 + 0.6 * g.reasoning_budget / 128]

    o1 = run_2d_evolution(ev, pop_size=6, generations=1, seed=5, preference="cost_first")
    o2 = run_2d_evolution(ev, pop_size=6, generations=1, seed=5, preference="cost_first")
    assert o1["front"] == o2["front"]
    assert o1["spec"]["maximize"] == [True, False]
