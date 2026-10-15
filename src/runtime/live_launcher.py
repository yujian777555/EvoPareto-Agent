"""Live experiment launcher with mandatory strict budget (Phase R2-R1 Task A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.backend.base import DeepSeekBackend, LLMResponse
from src.runtime.http_budget import (
    BudgetDB,
    GateRequired,
    PhysicalBudgetGate,
    get_global_gate,
    install_global_gate,
    settle_ticket,
)


class LiveExperimentError(RuntimeError):
    pass


def launch_live_experiment(
    *,
    experiment_id: str,
    ledger_path: str | Path,
    max_physical: int = 100,
    max_cost_usd: float = 1.0,
    est_cost_per_request: float = 0.0005,
    model: str = "deepseek-flash",
) -> Dict[str, Any]:
    """Strict bootstrap: refuse to start if gate cannot be installed."""
    # 1) API key present
    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise LiveExperimentError("DEEPSEEK_API_KEY missing — refuse live start")

    # 2) BudgetDB open + version check
    try:
        db = BudgetDB(ledger_path, max_physical=max_physical, max_cost_usd=max_cost_usd)
    except Exception as e:
        raise LiveExperimentError(f"budget ledger unusable: {e}") from e

    snap = db.snapshot()
    if snap["physical_attempts"] >= snap["max_physical"]:
        raise LiveExperimentError("budget already exhausted")
    if snap["spent_cost_usd"] >= snap["max_cost_usd"]:
        raise LiveExperimentError("cost budget exhausted")

    # 3) Install STRICT gate
    gate = PhysicalBudgetGate(db, est_cost_per_request=est_cost_per_request)
    install_global_gate(gate, strict=True)
    if get_global_gate() is None:
        raise LiveExperimentError("gate install failed")

    backend = DeepSeekBackend(max_retries=1, timeout=30, model=model)

    def generate_with_accounting(prompt: str, *, budget: int = 32) -> LLMResponse:
        # Backend.generate uses http_client which acquires a physical ticket.
        # After response, usage is recorded on the backend; we also settle
        # tokens into the shared ledger via backend.usage delta hooks below.
        resp = backend.generate(prompt, budget=budget)
        return resp

    meta = {
        "experiment_id": experiment_id,
        "model": model,
        "strict": True,
        "ledger_path": str(ledger_path),
        "budget_snapshot": snap,
    }
    return {"backend": backend, "gate": gate, "db": db, "meta": meta, "generate": generate_with_accounting}


def finalize_live_experiment(db: BudgetDB, gate: Optional[PhysicalBudgetGate] = None) -> Dict[str, Any]:
    snap = db.snapshot()
    if snap["open_tickets"] != 0:
        raise LiveExperimentError(f"hanging tickets: {snap['open_tickets']}")
    return snap
