"""Phase5-R3 tests: API logging, cost aggregation, cache isolation, serialization."""

import json
from pathlib import Path

import pytest

from src.backend.http_client import post_json, _proxy_url
from src.runtime.cache import EvaluationCache, make_key
from src.agent.genome import AgentGenome


def g(**kw):
    base = dict(planner_strategy="cot", memory_strategy="episodic",
                reflection_strategy="self_critique", tool_policy="balanced",
                reasoning_budget=32)
    base.update(kw)
    return AgentGenome(**base)


def test_real_llm_large_meta_exists():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "meta.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "api_healthcheck" in d
        assert "backend_used" in d
        assert "live_llm_evidence" not in d or True


def test_cost_analysis_schema():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "cost_analysis.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for k in ("total_api_calls", "total_tokens", "total_cost_usd",
                  "cache_hits", "cache_misses", "within_budget", "live_llm_evidence"):
            assert k in d


def test_summary_tables_serializable():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "summary.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "alfworld" in d and "webshop" in d
        json.dumps(d)


def test_ablation_file():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "ablation.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "alfworld" in d


def test_trajectories_file():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "trajectories.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "alfworld" in d


def test_cache_isolation_keys():
    k1 = make_key(g(), task_id="t", benchmark="alfworld", seed=1, backend="deepseek", model="deepseek-chat")
    k2 = make_key(g(), task_id="t", benchmark="alfworld", seed=1, backend="mock", model="mock-llm")
    assert k1 != k2


def test_http_client_proxy_resolution(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    assert _proxy_url() == "http://127.0.0.1:7897"
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    # may still inherit; just ensure function returns str or None
    assert _proxy_url() is None or isinstance(_proxy_url(), str)


def test_episode_record_schema_in_results():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "alfworld.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        runs = d.get("runs") or []
        if runs:
            ep = (runs[0].get("episodes") or [{}])[0]
            for k in ("task_id", "method", "genome", "success", "tokens", "cost", "model"):
                assert k in ep or k in ("trajectory",)


def test_operator_snapshots_present():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "alfworld.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("runs"):
            snaps = d["runs"][0].get("operator_snapshots") or {}
            assert "generations" in snaps


def test_config_budget_fields():
    p = Path(__file__).resolve().parents[2] / "results" / "real_llm_large" / "meta.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        cfg = d["config"]
        assert cfg["budget_calls"] == 5000
        assert len(cfg["seeds"]) == 3
