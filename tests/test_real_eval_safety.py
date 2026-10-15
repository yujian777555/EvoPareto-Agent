"""Phase5-R3 regression tests: no mock fallback, invalid success, budget gate."""

import pytest

from src.agent.genome import AgentGenome
from src.backend.base import DeepSeekBackend, MockLLMBackend
from src.benchmark.alfworld_real import ALFWorldRealAdapter
from src.evaluation.evaluation_kind import (
    REAL_LLM_FAILED,
    REAL_LLM_PROXY,
    SIMULATED,
    classify_experiment,
)
from src.runtime.agent_builder import AgentBuilder
from src.runtime.cache import EvaluationCache


class FailingBackend(MockLLMBackend):
    def generate(self, prompt, *, budget=32, **kwargs):
        raise RuntimeError("simulated API outage")


def g(**kw):
    base = dict(planner_strategy="cot", memory_strategy="episodic",
                reflection_strategy="self_critique", tool_policy="balanced",
                reasoning_budget=32)
    base.update(kw)
    return AgentGenome(**base)


def test_no_silent_mock_fallback_on_api_failure():
    ad = ALFWorldRealAdapter(n_tasks=3, seed=0, backend=FailingBackend(), cache=EvaluationCache())
    agent = AgentBuilder().build(g())
    ep = ad.run(agent)
    assert ep.n_tasks == 3
    for r in ep.results:
        assert r.success is False
        assert r.metadata.get("evaluation_kind") == REAL_LLM_FAILED
        assert r.tokens == 0
        assert str(r.metadata.get("api_status", "")).startswith("error:")


def test_empty_completion_is_not_success():
    class EmptyBackend(MockLLMBackend):
        def generate(self, prompt, *, budget=32, **kwargs):
            from src.backend.base import LLMResponse

            return LLMResponse(text="", tokens_prompt=1, tokens_completion=0, model="empty")

    b = DeepSeekBackend(api_key="x", model="deepseek-flash")
    # Direct check on backend semantics: empty text must raise.
    # Monkeypatch post_json to empty choice.
    import src.backend.base as base_mod

    def fake_post(*a, **k):
        return 200, {"choices": [{"message": {"content": "   "}}], "usage": {}}

    old = base_mod.OpenAICompatibleBackend.generate
    # Use http_client path via monkeypatch
    import src.backend.http_client as hc

    orig = hc.post_json
    hc.post_json = lambda *a, **k: (200, {"choices": [{"message": {"content": ""}}], "usage": {}})
    try:
        with pytest.raises(RuntimeError, match="empty"):
            b.generate("hi", budget=8)
    finally:
        hc.post_json = orig


def test_episode_records_provenance():
    ad = ALFWorldRealAdapter(n_tasks=2, seed=1, backend=MockLLMBackend(), cache=EvaluationCache())
    agent = AgentBuilder().build(g())
    ep, recs = ad.run_recorded(agent)
    meta = recs[0].metadata
    assert meta.get("backend") == "mock"
    assert "model" in meta
    assert "api_status" in meta or meta.get("cached") is True
    assert "cached" in meta
    assert meta.get("evaluation_kind") in (REAL_LLM_PROXY, SIMULATED, "real_llm_failed")


def test_budget_gate_before_requests():
    from experiments.run_real_llm_large import assert_budget_before_calls

    assert_budget_before_calls(100, 5000)
    with pytest.raises(RuntimeError, match="budget exceeded"):
        assert_budget_before_calls(9000, 5000)


def test_classification_taxonomy():
    assert classify_experiment("mock", api_ok=True) == SIMULATED
    assert classify_experiment("deepseek", api_ok=True) == REAL_LLM_PROXY
    assert classify_experiment("deepseek", api_ok=False) == REAL_LLM_FAILED
    assert classify_experiment("any", api_ok=True, native_env=True) == "real_environment"


def test_proxy_default_disabled(monkeypatch):
    from src.backend.http_client import _proxy_url

    monkeypatch.delenv("EVO_USE_PROXY", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    assert _proxy_url() is None


def test_model_id_unified():
    from src.backend.base import DeepSeekBackend

    assert DeepSeekBackend.model == "deepseek-flash"
