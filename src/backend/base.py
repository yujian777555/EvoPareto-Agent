"""LLM backend abstraction (Phase 4).

Unified interface:

    backend.generate(prompt) -> LLMResponse

API keys are **never** hard-coded. They are read from environment variables:

    OPENAI_API_KEY
    DEEPSEEK_API_KEY

`MockLLMBackend` keeps all tests offline and deterministic.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    text: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    model: str = "unknown"
    latency: float = 0.0
    cost: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return int(self.tokens_prompt) + int(self.tokens_completion)


class LLMBackend(ABC):
    """Minimal generate interface for agent runtime."""

    name: str = "base"
    model: str = "unknown"

    @abstractmethod
    def generate(self, prompt: str, *, budget: int = 32, **kwargs: Any) -> LLMResponse:
        """Return a completion for `prompt`."""

    def count_tokens(self, text: str) -> int:
        # Cheap heuristic: ~4 chars per token.
        return max(1, len(text) // 4)

    def estimate_cost(self, prompt: str, completion: str) -> float:
        """Default cost model: $ per 1K tokens (overridable)."""
        return 0.0


def get_env_key(name: str) -> Optional[str]:
    val = os.environ.get(name, "").strip()
    return val or None


# ------------------------------------------------------------------ #
# Mock (offline / tests)
# ------------------------------------------------------------------ #
class MockLLMBackend(LLMBackend):
    """Deterministic backend. No network. Different genomes → different behavior
    is achieved by the agent runtime; this backend is stable given (prompt, budget).
    """

    name = "mock"
    model = "mock-llm"

    def __init__(self, *, latency: float = 0.01, cost_per_1k: float = 0.0) -> None:
        self.latency = latency
        self.cost_per_1k = cost_per_1k
        self.calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0

    def usage(self) -> Dict[str, float]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "cost": self.total_cost,
        }

    def generate(self, prompt: str, *, budget: int = 32, **kwargs: Any) -> LLMResponse:
        self.calls += 1
        # Deterministic pseudo-completion derived from prompt + budget.
        digest = hashlib.sha256(f"{prompt}|{budget}".encode("utf-8")).hexdigest()
        # Produce a short plan-like text; length scales with budget.
        n_steps = max(1, min(8, budget // 8))
        text = f"PLAN[{digest[:8]}] steps={n_steps} " + " ".join(
            f"act{i}" for i in range(n_steps)
        )
        tp = self.count_tokens(prompt)
        tc = self.count_tokens(text)
        cost = (tp + tc) / 1000.0 * self.cost_per_1k
        self.total_prompt_tokens += tp
        self.total_completion_tokens += tc
        self.total_cost += cost
        return LLMResponse(
            text=text,
            tokens_prompt=tp,
            tokens_completion=tc,
            model=self.model,
            latency=self.latency,
            cost=cost,
        )


# ------------------------------------------------------------------ #
# OpenAI-compatible (OpenAI / DeepSeek both use this HTTP shape)
# ------------------------------------------------------------------ #
class OpenAICompatibleBackend(LLMBackend):
    """Chat-completions style backend using urllib (no hard dependency).

    Supports timeout, bounded retry with backoff, and token/cost accounting.
    Subclasses set base_url / api_key_env / default model.
    """

    name = "openai_compatible"
    model = "gpt-4o-mini"
    api_key_env = "OPENAI_API_KEY"
    base_url = "https://api.openai.com/v1/chat/completions"
    cost_per_1k_prompt = 0.00015
    cost_per_1k_completion = 0.0006

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
    ) -> None:
        self.api_key = api_key or get_env_key(self.api_key_env)
        if model:
            self.model = model
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = retry_backoff
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self.total_calls = 0

    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def usage(self) -> Dict[str, float]:
        return {
            "calls": self.total_calls,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "cost": self.total_cost,
        }

    def generate(self, prompt: str, *, budget: int = 32, **kwargs: Any) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError(
                f"missing API key: set ${self.api_key_env} or pass api_key="
            )
        import time

        from src.backend.http_client import post_json

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": int(budget) * 8,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        t0 = time.time()
        status, data = post_json(
            self.base_url,
            payload,
            headers,
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_backoff=self.retry_backoff,
        )
        latency = time.time() - t0
        if status >= 400:
            raise RuntimeError(f"LLM request failed status={status} body={str(data)[:200]}")
        if not data:
            # 200 + empty body is NOT success (P0 pollution rule).
            raise RuntimeError("LLM request returned empty body")

        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""
        if not str(text).strip():
            # Empty completion is NOT success.
            raise RuntimeError("LLM completion empty")

        usage = data.get("usage") or {}
        tp = int(usage.get("prompt_tokens", self.count_tokens(prompt)))
        tc = int(usage.get("completion_tokens", self.count_tokens(text)))
        cost = tp / 1000.0 * self.cost_per_1k_prompt + tc / 1000.0 * self.cost_per_1k_completion

        self.total_calls += 1
        self.total_prompt_tokens += tp
        self.total_completion_tokens += tc
        self.total_cost += cost

        return LLMResponse(
            text=text,
            tokens_prompt=tp,
            tokens_completion=tc,
            model=self.model,
            latency=latency,
            cost=cost,
            raw={"id": data.get("id"), "usage": usage, "status": status},
        )


class OpenAIBackend(OpenAICompatibleBackend):
    name = "openai"
    model = "gpt-4o-mini"
    api_key_env = "OPENAI_API_KEY"
    base_url = "https://api.openai.com/v1/chat/completions"


class DeepSeekBackend(OpenAICompatibleBackend):
    name = "deepseek"
    model = "deepseek-flash"  # unified model id (diagnostics + experiments)
    api_key_env = "DEEPSEEK_API_KEY"
    base_url = "https://api.deepseek.com/v1/chat/completions"
    cost_per_1k_prompt = 0.0001
    cost_per_1k_completion = 0.0002


def resolve_backend(kind: str = "mock", **kwargs: Any) -> LLMBackend:
    """Factory: 'mock' | 'openai' | 'deepseek'."""
    key = (kind or "mock").strip().lower()
    if key == "mock":
        return MockLLMBackend(**kwargs)
    if key == "openai":
        return OpenAIBackend(**kwargs)
    if key == "deepseek":
        return DeepSeekBackend(**kwargs)
    raise ValueError(f"unknown backend kind: {kind!r}")
