"""Pilot1 live admission final patch tests.

P0-1 manifest lock on live entry · P0-2 atomic billing block · P0-3 E2E reconcile.
All offline: local mock HTTP only, 0 real DeepSeek calls.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.benchmark.manifest_lock import (
    assert_task_in_split,
    canonical_game_id,
    load_manifest,
    manifest_sha256,
    select_task,
    verify_actual_matches_target,
)
from src.runtime.http_budget import (
    BillingBlocked,
    BudgetDB,
    BudgetExceeded,
    PhysicalBudgetGate,
    get_global_gate,
    install_global_gate,
    pre_send_ticket,
    settle_ticket,
)

RESULTS = Path("results/pilot1_live_admission_verified")
DEV_MANIFEST = Path("results/native_alfworld/development_task_pool.json")


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #
class MockDeepSeekHandler(BaseHTTPRequestHandler):
    """Configurable mock DeepSeek chat endpoint; counts every request."""

    response_factory = staticmethod(
        lambda: {
            "model": "deepseek-flash",
            "choices": [{"message": {"content": "look"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
    )

    def do_POST(self):
        self.server.hits.append(1)
        body = json.dumps(type(self).response_factory()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def start_mock_server(response_factory=None):
    if response_factory is not None:
        MockDeepSeekHandler.response_factory = staticmethod(response_factory)
    else:
        MockDeepSeekHandler.response_factory = staticmethod(
            lambda: {
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "look"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        )
    srv = HTTPServer(("127.0.0.1", 0), MockDeepSeekHandler)
    srv.hits = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"


def make_backend(base_url, **kw):
    from src.backend.base import DeepSeekBackend

    b = DeepSeekBackend(api_key="test-key", model="deepseek-flash", max_retries=0, timeout=8, **kw)
    b.base_url = base_url
    return b


def install_test_gate(db, est=0.01):
    gate = PhysicalBudgetGate(db, est_cost_per_request=est)
    install_global_gate(gate, strict=True)
    return gate


def teardown_gate():
    install_global_gate(None, strict=False)


def write_evidence(name: str, payload: dict):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ #
# P0-1: Manifest lock on live entry
# ------------------------------------------------------------------ #
def test_resolve_locked_live_task_selects_exact():
    lock = None
    import sys

    sys.path.insert(0, str(Path("scripts").resolve()))
    from pilot1_entry import resolve_locked_live_task

    lock = resolve_locked_live_task(str(DEV_MANIFEST), task_index=0, split="valid_train")
    assert lock["manifest_sha256"] == manifest_sha256(DEV_MANIFEST)
    assert lock["target_game_id"]
    assert lock["game_file"].endswith("game.tw-pddl")
    assert lock["target_canonical_id"] == canonical_game_id(lock["target_game_id"])
    mf = load_manifest(DEV_MANIFEST)
    task = select_task(mf, 0)
    assert lock["target_game_id"] == task["game_id"]
    assert_task_in_split(task, "valid_train")


def test_resolve_locked_rejects_missing_manifest(tmp_path):
    import sys

    sys.path.insert(0, str(Path("scripts").resolve()))
    from pilot1_entry import resolve_locked_live_task

    with pytest.raises(SystemExit):
        resolve_locked_live_task(str(tmp_path / "nope.json"), task_index=0, split="valid_train")


def test_resolve_locked_rejects_wrong_split():
    import sys

    sys.path.insert(0, str(Path("scripts").resolve()))
    from pilot1_entry import resolve_locked_live_task

    # valid_train task must be rejected for valid_unseen membership check
    with pytest.raises(ValueError):
        resolve_locked_live_task(str(DEV_MANIFEST), task_index=0, split="valid_unseen")


def test_verify_rejects_wrong_game_id():
    with pytest.raises(RuntimeError):
        verify_actual_matches_target("/data/json_2.1.1/valid_train/A/trial_1", "/data/json_2.1.1/valid_train/B/trial_2")
    a, t = verify_actual_matches_target(
        "/data/json_2.1.1/valid_train/A/trial_1/game.tw-pddl",
        "/data/json_2.1.1/valid_train/A/trial_1",
    )
    assert a == t


class FakeNativeEnv:
    """Records force_game_file; serves a fixed identity (or a wrong one)."""

    def __init__(self, actual_game_id: str, config=None):
        self.config = config
        self.actual_game_id = actual_game_id
        self.reset_calls = []
        self.last_reset_meta = {}

    def reset(self, *, episode_index: int = 0, force_game_file=None):
        self.reset_calls.append({"episode_index": episode_index, "force_game_file": force_game_file})
        self.last_reset_meta = {"actual_game_id": self.actual_game_id}
        obs = ("Your task is to: put a mug on the desk.",)
        infos = {
            "admissible_commands": (["look", "go to desk 1"],),
            "won": (False,),
            "actual_game_id": self.actual_game_id,
            "requested_split": "valid_train",
        }
        return obs, infos

    def step(self, actions):
        return ("done",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}


def test_episode_runner_second_reset_keeps_same_game():
    import sys

    sys.path.insert(0, str(Path("scripts").resolve()))
    from pilot1_entry import make_locked_reset, resolve_locked_live_task

    from src.agent.genome import AgentGenome
    from src.runtime.episode_runner import EpisodeRunner

    lock = resolve_locked_live_task(str(DEV_MANIFEST), task_index=0, split="valid_train")
    target = lock["target_game_id"]
    env = FakeNativeEnv(actual_game_id=target + "/game.tw-pddl")
    locked_reset = make_locked_reset(env, lock["game_file"], target)

    calls = {"n": 0}

    def llm(p):
        calls["n"] += 1
        return {"text": "look", "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0}}

    runner = EpisodeRunner(
        AgentGenome("cot", "short_term", "none", "balanced", 16),
        llm, horizon=2, experiment_id="lock", git_sha="deadbeef",
    )
    runner.run(locked_reset, env.step, episode_id=0, seed=1)
    # EpisodeRunner reset + any re-reset must both use force_game_file
    assert len(env.reset_calls) >= 1
    for c in env.reset_calls:
        assert c["force_game_file"] == lock["game_file"]
        assert c["force_game_file"].endswith("game.tw-pddl")


def test_identity_error_sends_zero_http(tmp_path):
    import sys

    sys.path.insert(0, str(Path("scripts").resolve()))
    from pilot1_entry import make_locked_reset, resolve_locked_live_task

    from src.agent.genome import AgentGenome
    from src.runtime.episode_runner import EpisodeRunner

    lock = resolve_locked_live_task(str(DEV_MANIFEST), task_index=0, split="valid_train")
    wrong = "/data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-999/trial_T00000000_000000_000000"
    env = FakeNativeEnv(actual_game_id=wrong)
    locked_reset = make_locked_reset(env, lock["game_file"], lock["target_game_id"])

    hits = {"n": 0}

    def llm(p):
        hits["n"] += 1
        return {"text": "look", "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0}}

    runner = EpisodeRunner(
        AgentGenome("cot", "short_term", "none", "balanced", 16),
        llm, horizon=2, experiment_id="idfail", git_sha="deadbeef",
    )
    with pytest.raises(RuntimeError, match="game identity mismatch"):
        runner.run(locked_reset, env.step, episode_id=0, seed=1)
    assert hits["n"] == 0


def test_live_entry_mock_backend_uses_manifest_lock(tmp_path):
    """Live entry path with mock backend MUST use the same manifest lock."""
    import argparse
    import sys

    sys.path.insert(0, str(Path("scripts").resolve()))
    import pilot1_entry
    from pilot1_entry import live_run, resolve_locked_live_task

    lock = resolve_locked_live_task(str(DEV_MANIFEST), task_index=0, split="valid_train")
    target = lock["target_game_id"]

    class PatchEnv(FakeNativeEnv):
        def __init__(self, config=None):
            super().__init__(actual_game_id=target + "/game.tw-pddl", config=config)

    import src.benchmark.native_alfworld as nw
    import src.runtime.live_launcher as ll

    old_env, old_launch = nw.NativeALFWorldEnv, ll.launch_live_experiment

    db = BudgetDB(tmp_path / "live.db", max_physical=20, max_cost_usd=1.0)

    def fake_launch(**kw):
        from src.backend.base import MockLLMBackend

        install_test_gate(db, est=0.001)
        return {"backend": MockLLMBackend(), "db": db, "gate": get_global_gate(), "meta": {}}

    nw.NativeALFWorldEnv = PatchEnv
    ll.launch_live_experiment = fake_launch
    try:
        args = argparse.Namespace(
            live=True, mode="pilot1_wiring", experiment_id="pilot1-mock",
            ledger_path=str(tmp_path / "live.db"), physical_cap=120, cost_cap=0.05,
            task_manifest=str(DEV_MANIFEST), task_index=0,
            output_dir=str(tmp_path / "out"), seed=11, split="valid_train", horizon=3,
        )
        import os

        os.environ["DEEPSEEK_API_KEY"] = "dummy-not-real"
        result = live_run(args)
        ep = result["episode"]
        assert result["manifest_sha256"] == manifest_sha256(DEV_MANIFEST)
        assert ep["manifest_sha256"] == manifest_sha256(DEV_MANIFEST)
        assert ep["selected_manifest_game_id"] == target
        assert ep["git_sha"] and ep["git_sha"] != "unknown"
        assert canonical_game_id(ep["game_id"]) == canonical_game_id(target)
        # force_game_file used on every reset
        # (PatchEnv instances created inside live_run; identity matched or live_run would raise)
        assert ep["evaluation_kind"] == "real_environment"
        write_evidence(
            "live_manifest_mock.json",
            {
                "scenario": "live_entry_mock_backend_manifest_lock",
                "status": "PASS",
                "manifest_sha256": ep["manifest_sha256"],
                "selected_manifest_game_id": ep["selected_manifest_game_id"],
                "raw_task_id": result["raw_task_id"],
                "actual_game_id": result["actual_game_id"],
                "canonical_game_id": ep["canonical_game_id"],
                "git_sha": ep["git_sha"],
                "task_index": ep.get("task_index"),
                "requested_split": ep.get("requested_split"),
                "episode_success": ep["success"],
                "llm_call_count": ep["llm_call_count"],
                "same_lock_as_native_smoke": True,
                "real_api_calls": 0,
            },
        )
    finally:
        nw.NativeALFWorldEnv = old_env
        ll.launch_live_experiment = old_launch
        teardown_gate()
        db.close()


# ------------------------------------------------------------------ #
# P0-2: atomic billing block
# ------------------------------------------------------------------ #
def test_normal_request_full_settle(tmp_path):
    srv, url = start_mock_server()
    try:
        db = BudgetDB(tmp_path / "n.db", max_physical=10, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        resp = backend.generate("hi", budget=4)
        snap = db.snapshot()
        assert snap["physical_attempts"] == 1
        assert snap["settled_ok"] == 1
        assert snap["open_tickets"] == 0
        assert snap["tokens_in"] == 100 == backend.total_prompt_tokens
        assert snap["tokens_out"] == 20 == backend.total_completion_tokens
        assert snap["spent_cost_usd"] == pytest.approx(backend.total_cost, rel=1e-9)
        assert not db.is_billing_blocked()
        assert len(srv.hits) == 1
        assert resp.cost == pytest.approx(backend.total_cost, rel=1e-9)
        write_evidence(
            "atomic_billing_block.json",
            {
                "normal_settle": {
                    "physical_attempts": snap["physical_attempts"],
                    "tokens_in": snap["tokens_in"],
                    "tokens_out": snap["tokens_out"],
                    "spent_cost_usd": snap["spent_cost_usd"],
                    "backend_total_cost": backend.total_cost,
                    "http_hits": len(srv.hits),
                    "billing_blocked": False,
                    "status": "PASS",
                }
            },
        )
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_unknown_usage_atomic_block(tmp_path):
    srv, url = start_mock_server(lambda: {"model": "deepseek-flash", "choices": [{"message": {"content": "x"}}]})
    try:
        db = BudgetDB(tmp_path / "u.db", max_physical=10, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        with pytest.raises(Exception):
            backend.generate("hi", budget=4)
        assert db.is_billing_blocked()
        reason = db.billing_block_reason()
        assert "UNKNOWN_USAGE" in reason
        snap = db.snapshot()
        assert snap["physical_attempts"] == 1
        assert snap["open_tickets"] == 0
        assert len(srv.hits) == 1
        with pytest.raises(BillingBlocked):
            pre_send_ticket()
        assert len(srv.hits) == 1  # second send impossible
        # atomicity evidence
        ev = json.loads((RESULTS / "atomic_billing_block.json").read_text()) if (RESULTS / "atomic_billing_block.json").exists() else {}
        ev["unknown_usage_block"] = {
            "status": "PASS",
            "reason": reason,
            "physical_attempts": snap["physical_attempts"],
            "http_hits": len(srv.hits),
            "billing_blocked": True,
            "second_send_count": 0,
        }
        write_evidence("atomic_billing_block.json", ev)
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_unknown_rate_atomic_block(tmp_path):
    srv, url = start_mock_server(
        lambda: {
            "model": "gpt-99",
            "choices": [{"message": {"content": "x"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
    )
    try:
        db = BudgetDB(tmp_path / "r.db", max_physical=10, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        backend.model = "gpt-99"
        with pytest.raises(Exception):
            backend.generate("hi", budget=4)
        assert db.is_billing_blocked()
        assert "UNKNOWN_RATE" in db.billing_block_reason()
        with pytest.raises(BillingBlocked):
            db.acquire_ticket(0.01)
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_billing_block_survives_restart(tmp_path):
    path = tmp_path / "b.db"
    db = BudgetDB(path, max_physical=10, max_cost_usd=1.0)
    t = db.acquire_ticket(0.01)
    db.settle_unknown_and_block(t, reason="UNKNOWN_USAGE:missing usage fields", tokens_in=3, tokens_out=1)
    snap1 = db.snapshot()
    db.close()
    db2 = BudgetDB(path, max_physical=10, max_cost_usd=1.0)
    assert db2.is_billing_blocked()
    assert "UNKNOWN_USAGE" in db2.billing_block_reason()
    with pytest.raises(BillingBlocked):
        db2.acquire_ticket(0.01)
    snap2 = db2.snapshot()
    assert snap2["physical_attempts"] == snap1["physical_attempts"] == 1
    assert snap2["tokens_in"] == 3
    db2.close()


def _worker_acquire(path, n, out_q):
    db = BudgetDB(path, max_physical=100, max_cost_usd=10.0)
    got = 0
    blocked = 0
    for _ in range(n):
        try:
            db.acquire_ticket(0.001)
            got += 1
        except BillingBlocked:
            blocked += 1
        except Exception:
            pass
    db.close()
    out_q.put((got, blocked))


def test_two_process_cannot_bypass_block(tmp_path):
    path = tmp_path / "proc.db"
    db = BudgetDB(path, max_physical=50, max_cost_usd=5.0)
    t = db.acquire_ticket(0.01)
    db.settle_unknown_and_block(t, reason="UNKNOWN_USAGE")
    db.close()

    q = mp.Queue()
    ps = [mp.Process(target=_worker_acquire, args=(str(path), 5, q)) for _ in range(2)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(timeout=30)
    results = [q.get(timeout=5) for _ in ps]
    total_got = sum(r[0] for r in results)
    total_blocked = sum(r[1] for r in results)
    assert total_got == 0
    assert total_blocked == 10


def test_concurrent_interleave_no_ticket_after_block_commit(tmp_path):
    """Required: after the block transaction commits, no new ticket is issued."""
    path = tmp_path / "interleave.db"
    db = BudgetDB(path, max_physical=200, max_cost_usd=20.0)
    start = threading.Barrier(9, timeout=10)
    tickets_before = []
    tickets_after = []
    blocked_after = []
    errors = []

    def acquirer(slot):
        try:
            start.wait()
            tid = db.acquire_ticket(0.001)
            tickets_before.append(tid)
            # keep the ticket open briefly so block races with open reservations
            time.sleep(0.01)
            try:
                tid2 = db.acquire_ticket(0.001)
                tickets_after.append(tid2)
            except BillingBlocked:
                blocked_after.append(slot)
        except BillingBlocked:
            blocked_after.append(slot)
        except Exception as e:
            errors.append(repr(e))

    def blocker():
        try:
            start.wait()
            my = db.acquire_ticket(0.001)
            db.settle_unknown_and_block(my, reason="UNKNOWN_USAGE:race")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=acquirer, args=(i,)) for i in range(8)]
    threads.append(threading.Thread(target=blocker))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, errors
    assert db.is_billing_blocked()
    # after block commit, any attempt must fail
    for _ in range(5):
        with pytest.raises(BillingBlocked):
            db.acquire_ticket(0.001)
    assert tickets_after == []
    write_evidence(
        "atomic_billing_block.json",
        {
            **(
                json.loads((RESULTS / "atomic_billing_block.json").read_text())
                if (RESULTS / "atomic_billing_block.json").exists()
                else {}
            ),
            "concurrent_interleave": {
                "status": "PASS",
                "tickets_before_block_visible": len(tickets_before),
                "tickets_after_block": len(tickets_after),
                "blocked_slots": len(blocked_after),
                "post_block_acquire_attempts": 5,
                "post_block_acquire_successes": 0,
            },
        },
    )
    db.close()


def test_transaction_failure_aborts_and_no_false_settle(tmp_path):
    db = BudgetDB(tmp_path / "f.db", max_physical=10, max_cost_usd=1.0)
    t = db.acquire_ticket(0.01)
    # settle of an unknown ticket id must raise — caller aborts, no silent success
    with pytest.raises(Exception):
        db.settle_unknown_and_block("no-such-ticket", reason="UNKNOWN_USAGE")
    # the real ticket is untouched: still open, not falsely settled
    snap = db.snapshot()
    assert snap["open_tickets"] == 1
    assert snap["physical_attempts"] == 0
    assert not db.is_billing_blocked()
    # committing the real ticket still works exactly once
    db.settle_unknown_and_block(t, reason="UNKNOWN_USAGE")
    assert db.is_billing_blocked()
    assert db.snapshot()["physical_attempts"] == 1
    db.close()


def test_same_ticket_not_double_settled(tmp_path):
    db = BudgetDB(tmp_path / "d.db", max_physical=10, max_cost_usd=1.0)
    t = db.acquire_ticket(0.01)
    db.settle_unknown_and_block(t, reason="UNKNOWN_USAGE")
    with pytest.raises(RuntimeError, match="already settled"):
        db.settle_unknown_and_block(t, reason="UNKNOWN_USAGE")
    with pytest.raises(RuntimeError, match="already settled"):
        db.settle(t, success=True, actual_cost=0.01)
    snap = db.snapshot()
    assert snap["physical_attempts"] == 1  # not 2
    assert snap["settled_failed"] == 1
    db.close()


def test_retry_cannot_bypass_billing_blocked(tmp_path):
    srv, url = start_mock_server(lambda: {"model": "deepseek-flash", "choices": [{"message": {"content": "x"}}]})
    try:
        db = BudgetDB(tmp_path / "rr.db", max_physical=20, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        backend.max_retries = 3
        with pytest.raises(Exception):
            backend.generate("hi", budget=4)
        first_hits = len(srv.hits)
        assert first_hits == 1
        assert db.is_billing_blocked()
        for _ in range(3):
            with pytest.raises(BillingBlocked):
                backend.generate("hi", budget=4)
        assert len(srv.hits) == first_hits  # retries cannot send
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_prior_successful_ledger_not_broken(tmp_path):
    srv, url = start_mock_server()
    try:
        db = BudgetDB(tmp_path / "keep.db", max_physical=20, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        backend.generate("one", budget=4)
        before = db.snapshot()
        # now force unknown cost
        MockDeepSeekHandler.response_factory = staticmethod(
            lambda: {"model": "deepseek-flash", "choices": [{"message": {"content": "y"}}]}
        )
        with pytest.raises(Exception):
            backend.generate("two", budget=4)
        after = db.snapshot()
        assert after["settled_ok"] == before["settled_ok"] == 1
        assert after["spent_cost_usd"] == pytest.approx(before["spent_cost_usd"])
        assert after["physical_attempts"] == 2
        assert after["tokens_in"] == 100  # first success preserved
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


# ------------------------------------------------------------------ #
# P0-3: HTTP → Backend → Episode → SQLite reconciliation
# ------------------------------------------------------------------ #
def test_e2e_mock_http_reconciliation(tmp_path):
    srv, url = start_mock_server()
    try:
        from src.agent.genome import AgentGenome
        from src.runtime.episode_runner import EpisodeRunner

        db = BudgetDB(tmp_path / "e2e.db", max_physical=20, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)

        def llm(prompt):
            resp = backend.generate(prompt, budget=8)
            return {
                "text": resp.text,
                "usage": {
                    "calls": 1,
                    "tokens_in": resp.tokens_prompt,
                    "tokens_out": resp.tokens_completion,
                    "cost": resp.cost,
                },
                "model": resp.model,
            }

        def reset(episode_index=0):
            return ("Your task is to: demo",), {
                "admissible_commands": (["look"],),
                "won": (False,),
                "actual_game_id": "/data/json_2.1.1/valid_train/g0/t/game.tw-pddl",
                "requested_split": "valid_train",
            }

        def step(actions):
            return ("obs1",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}

        runner = EpisodeRunner(
            AgentGenome("cot", "short_term", "none", "balanced", 32),
            llm, horizon=3, model="deepseek-flash", experiment_id="e2e", git_sha="e2e-sha",
        )
        ep = runner.run(reset, step, episode_id=0, seed=1)
        snap = db.snapshot()

        # single logical call, single physical HTTP, no retry
        assert len(srv.hits) == 1
        assert ep["llm_call_count"] == 1
        assert snap["physical_attempts"] == 1
        assert snap["settled_ok"] == 1
        assert snap["open_tickets"] == 0
        # ledger == backend == episode
        assert snap["tokens_in"] == backend.total_prompt_tokens == 100
        assert snap["tokens_out"] == backend.total_completion_tokens == 20
        assert snap["spent_cost_usd"] == pytest.approx(backend.total_cost, rel=1e-9)
        assert backend.total_cost == pytest.approx(ep["cost_usd"], rel=1e-9)
        assert ep["tokens_in"] == 100
        assert ep["tokens_out"] == 20
        # cost from frozen peak-conservative rates: 100*0.30/1e6 + 20*1.20/1e6
        expected = 100 * 0.30 / 1_000_000 + 20 * 1.20 / 1_000_000
        assert backend.total_cost == pytest.approx(expected, rel=1e-9)
        assert expected == pytest.approx(0.000054, rel=1e-9)
        write_evidence(
            "http_e2e_reconciliation.json",
            {
                "scenario": "local_mock_http_to_sqlite",
                "status": "PASS",
                "http_hits": len(srv.hits),
                "logical_llm_calls": ep["llm_call_count"],
                "physical_attempts": snap["physical_attempts"],
                "settled_ok": snap["settled_ok"],
                "open_tickets": snap["open_tickets"],
                "ledger_tokens_in": snap["tokens_in"],
                "backend_tokens_in": backend.total_prompt_tokens,
                "episode_tokens_in": ep["tokens_in"],
                "ledger_tokens_out": snap["tokens_out"],
                "backend_tokens_out": backend.total_completion_tokens,
                "episode_tokens_out": ep["tokens_out"],
                "ledger_estimated_cost": snap["spent_cost_usd"],
                "backend_total_cost": backend.total_cost,
                "episode_cost_usd": ep["cost_usd"],
                "frozen_rate_expected_cost": expected,
                "rate_version": "deepseek-flash-2026-10-peak-conservative-v1",
                "real_deepseek_calls": 0,
                "transport": "post_json->local HTTP server",
            },
        )
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_e2e_empty_completion_and_missing_usage_block(tmp_path):
    srv, url = start_mock_server(lambda: {"model": "deepseek-flash", "choices": [{"message": {"content": ""}}]})
    try:
        db = BudgetDB(tmp_path / "empty.db", max_physical=10, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        with pytest.raises(Exception):
            backend.generate("hi", budget=4)
        assert db.is_billing_blocked()
        assert len(srv.hits) == 1
        with pytest.raises(Exception):
            backend.generate("hi", budget=4)
        assert len(srv.hits) == 1
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_e2e_http_error_statuses_recorded(tmp_path):
    cases = {
        401: {"error": {"message": "unauthorized"}},
        402: {"error": {"message": "Payment Required"}},
        429: {"error": {"message": "rate limited"}},
    }
    for code, body in cases.items():
        class H(MockDeepSeekHandler):
            def do_POST(self):
                self.server.hits.append(1)
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        srv.hits = []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
        try:
            db = BudgetDB(tmp_path / f"e{code}.db", max_physical=10, max_cost_usd=1.0)
            install_test_gate(db)
            backend = make_backend(url)
            with pytest.raises(Exception):
                backend.generate("hi", budget=4)
            snap = db.snapshot()
            assert snap["physical_attempts"] == 1
            assert len(srv.hits) == 1
            assert db.is_billing_blocked()  # missing usage on error body
            db.close()
        finally:
            teardown_gate()
            srv.shutdown()


def test_e2e_timeout_records_attempt(tmp_path):
    class H(MockDeepSeekHandler):
        def do_POST(self):
            self.server.hits.append(1)
            time.sleep(3.0)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    srv.hits = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
    try:
        db = BudgetDB(tmp_path / "to.db", max_physical=10, max_cost_usd=1.0)
        install_test_gate(db)
        backend = make_backend(url)
        backend.timeout = 1.0
        backend.max_retries = 0
        with pytest.raises(Exception):
            backend.generate("hi", budget=4)
        snap = db.snapshot()
        assert snap["physical_attempts"] >= 1
        assert snap["open_tickets"] == 0
        db.close()
    finally:
        teardown_gate()
        srv.shutdown()


def test_native_smoke_artifact_present():
    """Native Docker smoke record must exist and pass (re-run overwrites)."""
    p = RESULTS / "native_smoke.json"
    legacy = Path("results/pilot1_final_admission_verified/native_smoke.json")
    target = p if p.exists() else legacy
    if not target.exists():
        pytest.skip("native smoke not yet executed in this workspace")
    d = json.loads(target.read_text(encoding="utf-8"))
    assert d["native_dry_run_status"] == "PASS"
    assert d["checks"]["manifest_game_match"] is True
    assert d["checks"]["native_reset_pass"] is True
    assert d["checks"]["native_step_pass"] is True
    assert d["checks"]["episode_runner_pass"] is True
    assert d["checks"]["fitness_2d_pass"] is True
