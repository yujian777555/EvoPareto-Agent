"""R4 execution budget policy — VERSIONED IN CODE (authorization facts).

These values are the execution strategy contract. They are NOT defined by the
config under verification. A config that redeclares cheaper numbers and
recomputes config_sha256 must still fail verification.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

POLICY_VERSION = "R4-BUDGET-POLICY-v1"

# Fixed arithmetic contract
POLICY: Dict[str, Any] = {
    "policy_version": POLICY_VERSION,
    "requests_formula": "240 + 240 * R",
    "base_requests": 240,
    "per_r_requests": 240,
    "safety_margin": 0.10,
    "token_in_per_req": (150, 400),
    "token_out_per_req": (150, 800),
    "worst_case_usd_per_req": 0.003,
    "formula_check": lambda base, per_r: "240 + 240 * R" if (base, per_r) == (240, 240) else "MISMATCH",
}

# Status values that permit any real HTTP (none of the PROPOSED statuses do)
HTTP_FORBIDDEN_STATUSES = frozenset(
    {
        "PROPOSED_PENDING_PLANNER_ACCEPTANCE",
        "PROPOSED",
        "DRAFT",
        "BLOCKED",
    }
)

# Execution authorization is a SEPARATE flag from budget/config validation
EXECUTION_AUTHORIZATION_REQUIRED_KEY = "execution_authorized"


def policy_mismatch(config_budget: Dict[str, Any]) -> str:
    """Return '' if config budget_caps match the versioned POLICY, else error code.

    Comparing against POLICY (not trusting config) is what prevents a
    hash-recompute bypass.
    """
    if not isinstance(config_budget, dict):
        return "BUDGET_POLICY_TYPE"

    def _num(name: str, got: Any, want: float | int) -> str:
        if got is None:
            return "BUDGET_POLICY_MISSING:%s" % name
        if isinstance(got, bool) or not isinstance(got, (int, float)):
            return "BUDGET_POLICY_TYPE:%s" % name
        gf = float(got)
        if gf != gf or gf in (float("inf"), float("-inf")):
            return "BUDGET_POLICY_NOT_FINITE:%s" % name
        if abs(gf - float(want)) > 1e-12:
            return "BUDGET_POLICY_MISMATCH:%s" % name
        return ""

    # formula: exact string
    formula = config_budget.get("requests_formula")
    if formula is None:
        return "BUDGET_POLICY_MISSING:requests_formula"
    if not isinstance(formula, str) or formula != POLICY["requests_formula"]:
        return "BUDGET_POLICY_MISMATCH:requests_formula"

    for name, want in (
        ("base_requests", POLICY["base_requests"]),
        ("per_r_requests", POLICY["per_r_requests"]),
    ):
        got = config_budget.get(name)
        if isinstance(got, bool) or not isinstance(got, int):
            return "BUDGET_POLICY_TYPE:%s" % name
        if got != want:
            return "BUDGET_POLICY_MISMATCH:%s" % name

    err = _num("safety_margin", config_budget.get("safety_margin"), POLICY["safety_margin"])
    if err:
        return err
    err = _num(
        "worst_case_usd_per_req",
        config_budget.get("worst_case_usd_per_req"),
        POLICY["worst_case_usd_per_req"],
    )
    if err:
        return err

    tin = config_budget.get("token_in_per_req")
    tout = config_budget.get("token_out_per_req")
    if tin is None or tout is None:
        return "BUDGET_POLICY_MISSING:tokens"
    if list(tin) != list(POLICY["token_in_per_req"]):
        return "BUDGET_POLICY_MISMATCH:token_in_per_req"
    if list(tout) != list(POLICY["token_out_per_req"]):
        return "BUDGET_POLICY_MISMATCH:token_out_per_req"
    return ""
