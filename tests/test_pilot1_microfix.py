"""Pilot1 microfix tests: manifest lock, billing block, E2E reconcile."""

import json
from pathlib import Path

import pytest

from src.benchmark.manifest_lock import (
    canonical_game_id,
    load_manifest,
    manifest_sha256,
    select_task,
    verify_actual_matches_target,
)
from src.runtime.http_budget import (
    BillingBlocked,
    BudgetDB,
    install_global_gate,
    pre_send_ticket,
)


def test_canonical_game_id_normalizes_tw_pddl():
    a = canonical_game_id("/data/x/trial_1/game.tw-pddl")
    b = canonical_game_id("/data/x/trial_1")
    assert a == b == "/data/x/trial_1"


def test_verify_actual_matches_target_exact():
    a, t = verify_actual_matches_target("/g/t/game.tw-pddl", "/g/t")
    assert a == t == "/g/t"
    with pytest.raises(RuntimeError):
        verify_actual_matches_target("/g/t1", "/g/t2")


def test_manifest_select_and_sha(tmp_path):
    mf = Path("results/native_alfworld/development_task_pool.json")
    assert mf.exists()
    sha1 = manifest_sha256(mf)
    data = load_manifest(mf)
    task = select_task(data, 0)
    assert task.get("game_id")
    assert manifest_sha256(mf) == sha1  # file unchanged


def test_unknown_cost_billing_block_persists(tmp_path):
    path = tmp_path / "b.db"
    db = BudgetDB(path, max_physical=10, max_cost_usd=1.0)
    db.mark_billing_blocked("UNKNOWN_USAGE", ticket_id="t1")
    db.close()
    db2 = BudgetDB(path, max_physical=10, max_cost_usd=1.0)
    assert db2.is_billing_blocked() is True
    with pytest.raises(BillingBlocked):
        db2.acquire_ticket(0.01)
    db2.close()


def test_unknown_cost_no_further_send(tmp_path):
    from src.backend.cost_status import UNKNOWN_USAGE, estimate_cost

    path = tmp_path / "b.db"
    db = BudgetDB(path, max_physical=10, max_cost_usd=1.0)
    gate_ok = db.acquire_ticket(0.01)
    db.settle(gate_ok, success=True, actual_cost=0.01)
    # simulate unknown cost event
    cs = estimate_cost("deepseek-flash", None, 1)
    assert cs.status == UNKNOWN_USAGE
    db.mark_billing_blocked(cs.status, ticket_id="uk1")
    with pytest.raises(BillingBlocked):
        pre_send_ticket() if False else db.acquire_ticket(0.01)


def test_native_smoke_strict_pass():
    p = Path("results/pilot1_final_admission_verified/native_smoke.json")
    assert p.exists(), "docker smoke with manifest lock required"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["checks"]["manifest_game_match"] is True
    assert d["native_dry_run_status"] == "PASS"
    assert all(d["checks"][k] for k in (
        "alfworld_importable", "manifest_valid", "manifest_game_match",
        "native_reset_pass", "native_step_pass", "episode_runner_pass",
        "fitness_2d_pass",
    ))
    ident = json.loads(Path("results/pilot1_final_admission_verified/task_identity.json").read_text(encoding="utf-8"))
    assert ident["canonical_game_id"]
    assert "valid_train" in ident["canonical_game_id"]
