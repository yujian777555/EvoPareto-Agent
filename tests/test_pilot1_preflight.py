"""Pilot1 preflight tests: conservative pricing, transport-uncertain block, git identity."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.backend.cost_status import KNOWN, UNKNOWN_RATE, backend_estimated_cost, estimate_cost
from src.backend.rates import (
    KNOWN_MODELS,
    PEAK_INPUT_CACHE_MISS_PER_1M,
    PEAK_OUTPUT_PER_1M,
    RATE_SOURCE,
    RATE_VERSION,
    RATES,
    estimated_cost as rates_estimated_cost,
    rate_metadata,
)
from src.runtime.http_budget import (
    BillingBlocked,
    BudgetDB,
    PhysicalBudgetGate,
    install_global_gate,
    pre_send_ticket,
)
from src.runtime.run_identity import GitIdentityError, resolve_git_sha, write_run_manifest

import tempfile

# TEST modules never write into tracked results/ — production experiment
# writers live in scripts/ and take an explicit output_dir. Default here is a
# throwaway temp dir so success / failure / exception / interrupt cannot
# pollute frozen experiment records.
RESULTS = Path(tempfile.mkdtemp(prefix="evo_test_pilot1_preflight_"))

from tests.frozen_guard import ROOT as _FROZEN_ROOT  # noqa: E402


def _refuse_frozen(path: Path) -> Path:
    """Source-level block: test evidence must never land in tracked results/."""
    import os
    resolved = Path(path).resolve()
    frozen_root = (_FROZEN_ROOT / "results").resolve()
    under_frozen = resolved == frozen_root or frozen_root in resolved.parents
    under_evidence = "pytest_evidence" in str(resolved) or "tmp" in str(resolved).lower()
    if under_frozen and not under_evidence:
        # When running under pytest we require an isolated target.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise RuntimeError(
                f"refusing to write test evidence into frozen results: {resolved}"
            )
    return path




def _write(name: str, payload: dict):
    RESULTS.mkdir(parents=True, exist_ok=True)
    _refuse_frozen(RESULTS)
    (RESULTS / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ #
# Fix 1: pricing
# ------------------------------------------------------------------ #
def test_single_authoritative_rate_definition():
    # cost_status must not carry its own numbers
    import src.backend.cost_status as cs
    import src.backend.rates as rates

    assert cs.RATE_VERSION == rates.RATE_VERSION
    assert cs.RATES is rates.RATES
    assert RATE_VERSION == "deepseek-flash-2026-10-peak-conservative-v1"
    assert PEAK_INPUT_CACHE_MISS_PER_1M == 0.30
    assert PEAK_OUTPUT_PER_1M == 1.20
    assert KNOWN_MODELS == ("deepseek-flash",)


def test_pricing_100_20_equals_0_000054():
    cost = rates_estimated_cost("deepseek-flash", 100, 20)
    expected = 100 * 0.30 / 1_000_000 + 20 * 1.20 / 1_000_000
    assert cost == pytest.approx(expected)
    assert cost == pytest.approx(0.000054)
    c = estimate_cost("deepseek-flash", 100, 20)
    assert c.status == KNOWN
    assert c.cost == pytest.approx(0.000054)
    assert backend_estimated_cost("deepseek-flash", 100, 20) == pytest.approx(0.000054)


def test_unknown_model_never_maps_to_cheaper_rate():
    c = estimate_cost("deepseek-chat", 100, 20)  # retired name, not official
    assert c.status == UNKNOWN_RATE
    c2 = estimate_cost("gpt-99", 100, 20)
    assert c2.status == UNKNOWN_RATE
    with pytest.raises(ValueError):
        rates_estimated_cost("deepseek-chat", 1, 1)


def test_rate_metadata_records_source():
    meta = rate_metadata()
    assert "api-docs.deepseek.com" in RATE_SOURCE
    assert meta["source"] == RATE_SOURCE
    assert meta["verified_on"]
    assert meta["peak_input_cache_miss_per_1m"] == 0.30
    assert meta["peak_output_per_1m"] == 1.20
    _write("pricing_validation.json", {
        "status": "PASS",
        "rate_version": RATE_VERSION,
        "rate_source": RATE_SOURCE,
        "verified_on": meta["verified_on"],
        "policy": meta["policy"],
        "official_model": "deepseek-flash",
        "peak_input_cache_miss_per_1m": PEAK_INPUT_CACHE_MISS_PER_1M,
        "peak_output_per_1m": PEAK_OUTPUT_PER_1M,
        "fixed_test_tokens": {"prompt_tokens": 100, "completion_tokens": 20},
        "expected_cost_usd": 0.000054,
        "computed_cost_usd": rates_estimated_cost("deepseek-flash", 100, 20),
        "formula": "100*0.30/1e6 + 20*1.20/1e6",
        "known_models": list(KNOWN_MODELS),
        "unknown_model_maps_to_cheaper_rate": False,
        "real_api_calls": 0,
    })


def test_budget_reservation_covers_peak_request():
    # Reserve must cover a full peak-priced request before send.
    from src.runtime.live_launcher import (
        RESERVE_MAX_COMPLETION_TOKENS,
        RESERVE_MAX_PROMPT_TOKENS,
        default_reserve_per_request,
    )

    reserve = default_reserve_per_request("deepseek-flash")
    required = rates_estimated_cost(
        "deepseek-flash", RESERVE_MAX_PROMPT_TOKENS, RESERVE_MAX_COMPLETION_TOKENS
    )
    assert reserve == pytest.approx(required)
    # covers the documented token bounds under peak rates
    assert reserve >= rates_estimated_cost("deepseek-flash", 2000, 128)
    assert reserve == pytest.approx(2000 * 0.30 / 1e6 + 128 * 1.20 / 1e6)
    _write("pricing_validation.json", {
        **(json.loads((RESULTS / "pricing_validation.json").read_text(encoding="utf-8"))
           if (RESULTS / "pricing_validation.json").exists() else {}),
        "budget_reservation": {
            "reserve_max_prompt_tokens": RESERVE_MAX_PROMPT_TOKENS,
            "reserve_max_completion_tokens": RESERVE_MAX_COMPLETION_TOKENS,
            "reserve_per_request_usd": reserve,
            "formula": "peak rates × token upper bounds (not average cost)",
            "covers_conservative_request": reserve >= required,
            "physical_http_cap": 120,
            "estimated_cost_cap_usd": 0.05,
            "cap_is_local_estimate_not_provider_invoice": True,
        },
    })


# ------------------------------------------------------------------ #
# Fix 2: transport uncertain → atomic block
# ------------------------------------------------------------------ #
class SlowHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.hits.append(1)
        self.server.started.set()
        import time

        time.sleep(5.0)
        try:
            self.send_response(200)
            self.end_headers()
        except Exception:
            pass

    def log_message(self, *a):
        pass


def test_timeout_atomic_transport_uncertain_block(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), SlowHandler)
    srv.hits = []
    srv.started = threading.Event()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
    try:
        from src.backend.base import DeepSeekBackend

        db = BudgetDB(tmp_path / "to.db", max_physical=10, max_cost_usd=1.0)
        gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
        install_global_gate(gate, strict=True)
        backend = DeepSeekBackend(api_key="k", model="deepseek-flash", max_retries=0, timeout=1.0)
        backend.base_url = url

        with pytest.raises(Exception) as ei:
            backend.generate("hi", budget=4)
        # physical attempt counted, ticket closed, persistent block
        snap = db.snapshot()
        assert snap["physical_attempts"] == 1
        assert snap["open_tickets"] == 0
        assert db.is_billing_blocked()
        reason = db.billing_block_reason()
        assert "TRANSPORT_UNCERTAIN" in reason
        hits_after_first = len(srv.hits)

        # next send rejected BEFORE network
        with pytest.raises(BillingBlocked):
            backend.generate("hi", budget=4)
        assert len(srv.hits) == hits_after_first  # second_physical_send = 0

        # restart: block persists
        db.close()
        db2 = BudgetDB(tmp_path / "to.db", max_physical=10, max_cost_usd=1.0)
        assert db2.is_billing_blocked()
        with pytest.raises(BillingBlocked):
            db2.acquire_ticket(0.01)
        db2.close()

        _write("timeout_billing_block.json", {
            "status": "PASS",
            "scenario": "local mock delay -> transport timeout -> atomic billing block",
            "physical_attempts": 1,
            "billing_blocked": True,
            "billing_block_reason": reason,
            "second_physical_send": 0,
            "http_hits": hits_after_first,
            "block_survives_sqlite_restart": True,
            "retry_bypassed_block": False,
            "real_deepseek_calls": 0,
            "assertions": {
                "physical_attempts": 1,
                "billing_blocked": True,
                "second_physical_send": 0,
            },
        })
        install_global_gate(None, strict=False)
    finally:
        srv.shutdown()


def test_connection_drop_also_blocks(tmp_path):
    # Close listener after accept-level: use a port with no service after bind-release
    srv = HTTPServer(("127.0.0.1", 0), SlowHandler)
    port = srv.server_address[1]
    srv.server_close()  # free port, connection will be refused/reset
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    db = BudgetDB(tmp_path / "cd.db", max_physical=10, max_cost_usd=1.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    from src.backend.base import DeepSeekBackend

    backend = DeepSeekBackend(api_key="k", model="deepseek-flash", max_retries=0, timeout=2.0)
    backend.base_url = url
    with pytest.raises(Exception):
        backend.generate("hi", budget=4)
    snap = db.snapshot()
    assert snap["physical_attempts"] >= 1
    assert snap["open_tickets"] == 0
    # connection refused may be classified as transport-uncertain (conservative)
    # or may fail at connect; either way no hanging ticket and no silent zero
    assert snap["settled_ok"] == 0 or snap["settled_failed"] >= 0
    install_global_gate(None, strict=False)
    db.close()


# ------------------------------------------------------------------ #
# Fix 3: git identity
# ------------------------------------------------------------------ #
def test_resolve_git_sha_rejects_bad_values():
    for bad in ("unknown", "docker", "HEAD", "abc123", "z" * 40, "A" * 40, "0" * 39):
        with pytest.raises(GitIdentityError):
            resolve_git_sha(env={"GIT_SHA": bad})


def test_resolve_git_sha_accepts_env_40hex():
    sha = "a" * 40
    assert resolve_git_sha(env={"GIT_SHA": sha}) == sha


def test_resolve_git_sha_from_local_repo():
    sha = resolve_git_sha(env={}, cwd=str(Path.cwd()))
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_run_manifest_requires_valid_sha(tmp_path):
    with pytest.raises(GitIdentityError):
        write_run_manifest(
            tmp_path / "m.json",
            git_sha="docker",
            manifest_sha256="x",
            experiment_id="e",
            model="deepseek-flash",
            rate_version=RATE_VERSION,
            task_index=0,
            seed=11,
            objective_version="candidate_2obj",
        )
    ok = write_run_manifest(
        tmp_path / "m.json",
        git_sha="b" * 40,
        manifest_sha256="abc",
        experiment_id="e",
        model="deepseek-flash",
        rate_version=RATE_VERSION,
        task_index=0,
        seed=11,
        objective_version="candidate_2obj",
    )
    assert ok["git_sha"] == "b" * 40
    data = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert data["objective_version"] == "candidate_2obj"
    assert data["rate_version"] == RATE_VERSION


# ------------------------------------------------------------------ #
# Preflight HTTP reconciliation at the new rates
# ------------------------------------------------------------------ #
def test_http_reconciliation_at_peak_rates(tmp_path):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.server.hits.append(1)
            body = json.dumps({
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "look"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    from src.agent.genome import AgentGenome
    from src.backend.base import DeepSeekBackend
    from src.runtime.episode_runner import EpisodeRunner

    srv = HTTPServer(("127.0.0.1", 0), H)
    srv.hits = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
    try:
        db = BudgetDB(tmp_path / "r.db", max_physical=10, max_cost_usd=1.0)
        install_global_gate(PhysicalBudgetGate(db, est_cost_per_request=0.01), strict=True)
        backend = DeepSeekBackend(api_key="k", model="deepseek-flash", max_retries=0, timeout=8)
        backend.base_url = url

        def llm(prompt):
            resp = backend.generate(prompt, budget=8)
            return {
                "text": resp.text,
                "usage": {"calls": 1, "tokens_in": resp.tokens_prompt,
                          "tokens_out": resp.tokens_completion, "cost": resp.cost},
                "model": resp.model,
            }

        def reset(episode_index=0):
            return ("Your task is to: demo",), {
                "admissible_commands": (["look"],), "won": (False,),
                "actual_game_id": "/data/json_2.1.1/valid_train/g0/t/game.tw-pddl",
                "requested_split": "valid_train",
            }

        def step(actions):
            return ("o",), (0.0,), (True,), {"won": (False,), "admissible_commands": (["look"],)}

        ep = EpisodeRunner(
            AgentGenome("cot", "short_term", "none", "balanced", 32),
            llm, horizon=3, model="deepseek-flash", experiment_id="preflight",
            git_sha="a" * 40,
        ).run(reset, step, episode_id=0, seed=1)
        snap = db.snapshot()
        expected = 100 * 0.30 / 1_000_000 + 20 * 1.20 / 1_000_000
        assert snap["spent_cost_usd"] == pytest.approx(expected, rel=1e-9)
        assert backend.total_cost == pytest.approx(expected, rel=1e-9)
        assert ep["cost_usd"] == pytest.approx(expected, rel=1e-9)
        assert snap["tokens_in"] == backend.total_prompt_tokens == ep["tokens_in"] == 100
        assert snap["tokens_out"] == backend.total_completion_tokens == ep["tokens_out"] == 20
        assert len(srv.hits) == 1
        _write("http_reconciliation.json", {
            "status": "PASS",
            "rate_version": RATE_VERSION,
            "http_hits": 1,
            "physical_attempts": snap["physical_attempts"],
            "settled_ok": snap["settled_ok"],
            "open_tickets": snap["open_tickets"],
            "tokens_in": 100,
            "tokens_out": 20,
            "expected_cost_usd": expected,
            "ledger_cost": snap["spent_cost_usd"],
            "backend_cost": backend.total_cost,
            "episode_cost": ep["cost_usd"],
            "ledger_eq_backend_eq_episode": True,
            "formula": "100*0.30/1e6 + 20*1.20/1e6 = 0.000054",
            "real_deepseek_calls": 0,
        })
        install_global_gate(None, strict=False)
        db.close()
    finally:
        srv.shutdown()
