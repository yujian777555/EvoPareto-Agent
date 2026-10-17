"""Level 3-R1 regression tests: prompt contract, ledger, replay (offline)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.candidate_bundle import (
    BundleValidationError,
    PromptContractError,
    build_bundle,
    load_bundle_from_live_responses,
    normalize_prompt_module,
)
from src.runtime.auth_budget import AuthBudgetLedger, resolve_auth_identity

LIVE = ROOT / "results" / "level3_live_calibration"
R1 = ROOT / "results" / "level3_live_calibration_r1"

GRAPH_OK = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        return await self.llm(problem)\n"
)


# ---------------- Task A: prompt contract ----------------

def test_plain_text_prompt_serialises_to_instruction_repr():
    mod = normalize_prompt_module("You are a careful math solver.")
    assert mod.startswith("INSTRUCTION = ")
    compile(mod, "<p>", "exec")
    ns = {}
    exec(mod, ns)
    assert ns["INSTRUCTION"] == "You are a careful math solver."


def test_already_python_prompt_passthrough():
    src = "INSTRUCTION = 'hello'\n"
    assert normalize_prompt_module(src) == src


def test_empty_prompt_rejected():
    with pytest.raises(PromptContractError):
        normalize_prompt_module("")
    with pytest.raises(PromptContractError):
        normalize_prompt_module("   ")


def test_bundle_keeps_graph_bytes_and_hashes_prompt():
    prompt_text = "Be careful and end with #### n."
    b = build_bundle(graph_src=GRAPH_OK, prompt_field=prompt_text, modification="m")
    assert b.graph_src == GRAPH_OK  # never rewritten
    assert b.prompt_raw_sha256 != b.prompt_module_sha256  # raw vs serialised
    assert b.bundle_sha256
    assert b.graph_compile_ok and b.prompt_compile_ok
    ns = {}
    exec(b.prompt_module, ns)
    assert ns["INSTRUCTION"] == prompt_text


def test_bundle_rejects_invalid_graph():
    with pytest.raises(BundleValidationError):
        build_bundle(graph_src="class Workflow:\n    def broken(:\n", prompt_field="x")


def test_bundle_rejects_missing_workflow_class():
    with pytest.raises(BundleValidationError):
        build_bundle(graph_src="def f(): pass\n", prompt_field="x")


def test_bundle_rejects_empty_graph():
    with pytest.raises(BundleValidationError):
        build_bundle(graph_src="  ", prompt_field="x")


def test_real_live_candidate_bundle_loads():
    src = LIVE / "real_model_responses.json"
    assert src.exists()
    b = load_bundle_from_live_responses(src)
    assert b.graph_compile_ok
    assert b.prompt_compile_ok
    # graph SHA must match the live run's recorded candidate
    cand = json.loads((LIVE / "candidate_validation.json").read_text(encoding="utf-8"))
    assert b.graph_sha256 == cand.get("CANDIDATE_GRAPH_SHA")


# ---------------- Task B: budget ledger ----------------

def test_actual_vs_reserved_separated(tmp_path):
    led = AuthBudgetLedger(
        tmp_path / "a.sqlite", max_physical=10, max_cost_usd=1.0,
        max_total_in=10000, max_total_out=5000,
    )
    led.reserve(run_id="r1", logical_id="L1", physical_id="P1",
                phase="optimizer", prompt_sha="abc",
                res_in=400, res_out=500, res_cost=0.003)
    snap = led.snapshot()
    assert snap["reserved_tokens_in"] == 400
    assert snap["actual_tokens_in"] == 0
    led.settle_actual(physical_id="P1", actual_in=105, actual_out=333,
                      observed_cost=0.0004, http_status=200,
                      model_returned="deepseek-flash", finish_reason="stop")
    snap = led.snapshot()
    assert snap["actual_tokens_in"] == 105
    assert snap["actual_tokens_out"] == 333
    assert snap["reserved_tokens_in"] == 0  # released
    led.close()


def test_historical_actuals_are_162_454():
    d = json.loads((LIVE / "request_ledger.json").read_text(encoding="utf-8"))
    ain = sum(int(r.get("usage_prompt_tokens") or 0) for r in d["rows"])
    aout = sum(int(r.get("usage_completion_tokens") or 0) for r in d["rows"])
    assert ain == 162
    assert aout == 454


def test_auth_identity_survives_db_delete(tmp_path):
    p = tmp_path / "b.sqlite"
    led = AuthBudgetLedger(p, max_physical=5, max_cost_usd=1.0,
                           max_total_in=1000, max_total_out=1000)
    ident1 = led.auth_id
    led.reserve(run_id="r", logical_id="L", physical_id="P",
                phase="x", prompt_sha="s", res_in=10, res_out=10, res_cost=0.01)
    led.close()
    p.unlink()  # delete the DB
    led2 = AuthBudgetLedger(tmp_path / "c.sqlite", max_physical=5, max_cost_usd=1.0,
                            max_total_in=1000, max_total_out=1000)
    assert led2.auth_id == ident1  # identity unchanged
    # a NEW db starts fresh physically, but the auth identity is what quota
    # would be bound to in production; here we assert identity stability.
    led2.close()


def test_unknown_usage_blocks_persistently(tmp_path):
    led = AuthBudgetLedger(tmp_path / "c.sqlite", max_physical=10, max_cost_usd=1.0,
                           max_total_in=1000, max_total_out=1000)
    led.reserve(run_id="r", logical_id="L", physical_id="P",
                phase="x", prompt_sha="s", res_in=10, res_out=10, res_cost=0.01)
    led.settle_unknown_and_block(physical_id="P", reason="MISSING_USAGE")
    snap = led.snapshot()
    assert snap["blocked"] == 1
    assert snap["unknown_usage_count"] == 1
    with pytest.raises(RuntimeError, match="BUDGET_BLOCKED"):
        led.reserve(run_id="r", logical_id="L2", physical_id="P2",
                    phase="x", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
    led.close()


def test_cost_cap_enforced_before_send(tmp_path):
    led = AuthBudgetLedger(tmp_path / "d.sqlite", max_physical=10, max_cost_usd=0.002,
                           max_total_in=100000, max_total_out=100000)
    with pytest.raises(RuntimeError, match="MAX_COST"):
        led.reserve(run_id="r", logical_id="L", physical_id="P",
                    phase="x", prompt_sha="s", res_in=8000, res_out=500, res_cost=0.003)
    led.close()


def test_physical_cap_enforced(tmp_path):
    led = AuthBudgetLedger(tmp_path / "e.sqlite", max_physical=2, max_cost_usd=1.0,
                           max_total_in=100000, max_total_out=100000)
    for i in range(2):
        led.reserve(run_id="r", logical_id=f"L{i}", physical_id=f"P{i}",
                    phase="x", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
    with pytest.raises(RuntimeError, match="MAX_PHYSICAL"):
        led.reserve(run_id="r", logical_id="L9", physical_id="P9",
                    phase="x", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
    led.close()


def test_total_token_cap_enforced(tmp_path):
    led = AuthBudgetLedger(tmp_path / "f.sqlite", max_physical=10, max_cost_usd=1.0,
                           max_total_in=100, max_total_out=100)
    led.reserve(run_id="r", logical_id="L", physical_id="P",
                phase="x", prompt_sha="s", res_in=80, res_out=80, res_cost=0.001)
    with pytest.raises(RuntimeError, match="MAX_TOTAL"):
        led.reserve(run_id="r", logical_id="L2", physical_id="P2",
                    phase="x", prompt_sha="s", res_in=50, res_out=1, res_cost=0.001)
    led.close()


def test_concurrent_reserve_cannot_break_caps(tmp_path):
    import threading

    led = AuthBudgetLedger(tmp_path / "g.sqlite", max_physical=5, max_cost_usd=1.0,
                           max_total_in=100000, max_total_out=100000)
    errors = []

    def worker(n):
        for i in range(5):
            try:
                led.reserve(run_id="r", logical_id=f"{n}-{i}", physical_id=f"P{n}-{i}",
                            phase="x", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
            except Exception as e:
                errors.append(str(e)[:40])

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = led.snapshot()
    assert snap["physical_attempts"] <= 5
    assert any("MAX_PHYSICAL" in e for e in errors)
    led.close()


# ---------------- Task C: replay evidence ----------------

def test_replay_executed_real_graph():
    d = json.loads((R1 / "replay_execution.json").read_text(encoding="utf-8"))
    assert d["WORKFLOW_EXECUTABLE"] is True
    assert d["DOCKER_EXECUTION_STATUS"] == "PASS"
    assert d["IPC_REACHED"] is True
    assert d["IPC_PROCESSED"] >= 1
    assert d["BUNDLE_LOAD_VALID"] is True
    assert d["PROMPT_CONTRACT_VALID"] is True
    assert d["graph_rewritten"] is False
    assert d["gold_in_container"] is False


def test_replay_graph_sha_matches_live():
    live = json.loads((LIVE / "candidate_validation.json").read_text(encoding="utf-8"))
    rep = json.loads((R1 / "replay_execution.json").read_text(encoding="utf-8"))
    assert rep["ORIGINAL_GRAPH_SHA"] == live["CANDIDATE_GRAPH_SHA"]


def test_replay_negative_cases_rejected():
    d = json.loads((R1 / "replay_negative_tests.json").read_text(encoding="utf-8"))
    n = d["negatives"]
    assert n["missing_prompt"].startswith("REJECTED")
    assert n["invalid_python"].startswith("REJECTED")
    assert n["missing_workflow"].startswith("REJECTED")
    assert n["wrong_dependency"] == "PASS_EXEC_FAILED"


def test_replay_deterministic_from_saved_output():
    """Rebuilding the bundle from saved responses yields identical SHAs."""
    b1 = load_bundle_from_live_responses(LIVE / "real_model_responses.json")
    b2 = load_bundle_from_live_responses(LIVE / "real_model_responses.json")
    assert b1.graph_sha256 == b2.graph_sha256
    assert b1.prompt_module_sha256 == b2.prompt_module_sha256
    assert b1.bundle_sha256 == b2.bundle_sha256


# ---------------- Task D: taxonomy ----------------

def test_taxonomy_distinguishes_stages():
    d = json.loads((R1 / "evidence_taxonomy.json").read_text(encoding="utf-8"))
    live = d["live_level3_original"]
    rep = d["l3r1_replay"]
    # XML valid but prompt contract invalid in the original
    assert live["XML_VALID"] is True
    assert live["PROMPT_CONTRACT_VALID"] is False
    assert live["WORKFLOW_EXECUTABLE"] is False
    # replay fixed the contract
    assert rep["PROMPT_CONTRACT_VALID"] is True
    assert rep["WORKFLOW_EXECUTABLE"] is True
    # thinking mode is NOT independently verified
    assert d["thinking_disabled"]["independently_verifiable"] is False
    # original report preserved
    assert d["original_failure_report_preserved"] is True
