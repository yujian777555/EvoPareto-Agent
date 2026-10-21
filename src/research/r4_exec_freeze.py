"""R4 execution freeze (separate from confirmation-set freeze) + fail-closed verifier.

Three distinct verification layers — never conflated:

1. **Config structure & hash** — `verify_exec_config_structure`
2. **Budget feasibility vs a supplied auth snapshot** — `verify_budget_feasibility`
3. **Real authorization state** — read-only check via `load_auth_snapshot` (never creates/resets)

Zero model calls. Any missing field, illegal number, overflow, or cap breach
returns a stable non-empty error code. Config hash correctness is NEVER
treated as evidence of budget sufficiency.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.research.r4_budget_policy import (
    HTTP_FORBIDDEN_STATUSES,
    POLICY,
    POLICY_VERSION,
    policy_mismatch,
)

__all__ = [
    "DEFAULT_EXEC_FREEZE",
    "BudgetRequirements",
    "AuthSnapshot",
    "canonical_config_sha256",
    "compute_budget_requirements",
    "load_auth_snapshot",
    "verify_exec_config_structure",
    "verify_budget_feasibility",
    "verify_exec_freeze",
    "verify_execution_allowed",
    "POLICY_VERSION",
    "build_exec_freeze",
    "REQUESTS_FORMULA",
    "SAFETY_MARGIN",
]

BASE_SEED = 20260601
EXPECTED_PARENT_GRAPH_SHA = "ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e"
EXPECTED_PARENT_LF_SHA = "a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe"
EXPECTED_PARENT_PROMPT_SHA = "34b149ab37e571def0875faeac171867c3a2bb9fff03db4bc0ccca034e48e979"
EXPECTED_CONFIRM_V1_SHA = "1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4"
EXPECTED_TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"

REQUESTS_FORMULA = "240 + 240 * R"
SAFETY_MARGIN = 0.10
WORST_TOKEN_IN_PER_REQ = 400
WORST_TOKEN_OUT_PER_REQ = 800
WORST_USD_PER_REQ = 0.003

REQUIRED_KEYS = (
    "version",
    "created_for",
    "baseline_commit",
    "parent_artefacts",
    "mutation_plan",
    "seeds",
    "pairing_blocks",
    "operator_policy",
    "selection_rules",
    "datasets",
    "evaluation",
    "endpoints",
    "budget_caps",
    "config_sha256",
)

# Hard arithmetic ceilings to catch overflow / absurd values before math
_MAX_REQ = 10 ** 9
_MAX_TOKEN = 10 ** 12
_MAX_USD = 10 ** 9


class BudgetError(ValueError):
    """Illegal budget input (not a cap breach)."""


class AuthError(ValueError):
    """Authorization snapshot missing or corrupt."""


class BudgetRequirements(dict):
    """Pure computed requirements for one R. Dict for easy JSON/logging."""

    pass


class AuthSnapshot(dict):
    """Read-only view of authorization caps + consumed. Never mutated by verifier."""

    pass


def compute_budget_requirements(
    r: int,
    *,
    safety_margin: float = SAFETY_MARGIN,
    token_in_high: int = WORST_TOKEN_IN_PER_REQ,
    token_out_high: int = WORST_TOKEN_OUT_PER_REQ,
    usd_per_req: float = WORST_USD_PER_REQ,
    base_requests: int = 240,
    per_r_requests: int = 240,
) -> BudgetRequirements:
    """Pure budget arithmetic for Plan C-style total requests.

    TOTAL = base_requests + per_r_requests * R
    WITH_MARGIN = ceil(TOTAL * (1 + safety_margin))

    Raises BudgetError on illegal / overflowing inputs. Never silently clamps.
    """
    def _finite(name, v):
        if isinstance(v, bool):
            raise BudgetError("%s_NOT_NUMBER" % name)
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise BudgetError("%s_NOT_FINITE" % name)
        return v

    if isinstance(r, bool) or not isinstance(r, int):
        raise BudgetError("R_NOT_INT")
    if r < 0:
        raise BudgetError("R_NEGATIVE")
    if r > _MAX_REQ:
        raise BudgetError("R_OVERFLOW")
    safety_margin = _finite("MARGIN", safety_margin)
    if not isinstance(safety_margin, (int, float)) or isinstance(safety_margin, bool):
        raise BudgetError("MARGIN_NOT_NUMBER")
    if not (0.0 <= safety_margin <= 1.0):
        raise BudgetError("MARGIN_OUT_OF_RANGE")
    for name, v in (("token_in_high", token_in_high), ("token_out_high", token_out_high)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise BudgetError("%s_NOT_INT" % name)
        if v < 0:
            raise BudgetError("%s_NEGATIVE" % name)
        if v > _MAX_TOKEN:
            raise BudgetError("%s_OVERFLOW" % name)
    usd_per_req = _finite("USD", usd_per_req)
    if isinstance(usd_per_req, bool) or not isinstance(usd_per_req, (int, float)):
        raise BudgetError("USD_NOT_NUMBER")
    if usd_per_req < 0:
        raise BudgetError("USD_NEGATIVE")
    if usd_per_req > _MAX_USD:
        raise BudgetError("USD_OVERFLOW")

    try:
        total = base_requests + per_r_requests * r
        if total > _MAX_REQ:
            raise BudgetError("TOTAL_REQ_OVERFLOW")
        # exact ceil(total * (1+margin)) via Fraction — float 1.1*1680 is 1848.000…2
        from fractions import Fraction

        m = Fraction(safety_margin).limit_denominator(1000000)
        with_margin = int(math.ceil(Fraction(total) * (1 + m)))
        tok_in = total * token_in_high
        tok_out = total * token_out_high
        tok_in_m = with_margin * token_in_high
        tok_out_m = with_margin * token_out_high
        usd = total * float(usd_per_req)
        usd_m = with_margin * float(usd_per_req)
    except OverflowError as exc:
        raise BudgetError("ARITH_OVERFLOW:%s" % type(exc).__name__) from exc

    return BudgetRequirements(
        r=r,
        safety_margin=float(safety_margin),
        total_requests=total,
        requests_with_margin=with_margin,
        tokens_in_worst=tok_in,
        tokens_out_worst=tok_out,
        tokens_in_with_margin=tok_in_m,
        tokens_out_with_margin=tok_out_m,
        usd_worst=usd,
        usd_with_margin=usd_m,
    )


def load_auth_snapshot(path: Optional[Path] = None) -> AuthSnapshot:
    """READ-ONLY load of the authorization record. Never creates or resets it.

    Raises AuthError if missing or corrupt. Callers must not write this file.
    """
    p = path or (Path.home() / ".evopareto" / "state" / "level3_pilot_authorization.json")
    if not p.exists():
        raise AuthError("AUTH_FILE_MISSING")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuthError("AUTH_PARSE_ERROR:%s" % type(exc).__name__) from exc
    if not isinstance(raw, dict):
        raise AuthError("AUTH_NOT_OBJECT")
    caps = raw.get("caps")
    consumed = raw.get("consumed")
    if not isinstance(caps, dict) or not isinstance(consumed, dict):
        raise AuthError("AUTH_SCHEMA")
    try:
        max_req = int(caps["max_physical"])
        max_in = int(caps["max_total_in"])
        max_out = int(caps["max_total_out"])
        max_usd = float(caps["max_cost_usd"])
        cons_req = int(consumed.get("physical_attempts", 0))
        cons_in = int(consumed.get("actual_tokens_in", 0) or 0)
        cons_out = int(consumed.get("actual_tokens_out", 0) or 0)
        spent = float(consumed.get("spent_cost_usd", 0.0))
    except Exception as exc:
        raise AuthError("AUTH_FIELD_INVALID:%s" % type(exc).__name__) from exc
    if cons_req < 0 or cons_in < 0 or cons_out < 0 or spent < 0:
        raise AuthError("AUTH_CONSUMED_NEGATIVE")
    if cons_req > max_req or cons_in > max_in or cons_out > max_out:
        raise AuthError("AUTH_CONSUMED_EXCEEDS_CAP")
    snap = AuthSnapshot(
        max_requests=max_req,
        max_tokens_in=max_in,
        max_tokens_out=max_out,
        max_cost_usd=max_usd,
        consumed_requests=cons_req,
        consumed_tokens_in=cons_in,
        consumed_tokens_out=cons_out,
        spent_usd=spent,
        remaining_requests=max_req - cons_req,
        remaining_tokens_in=max_in - cons_in,
        remaining_tokens_out=max_out - cons_out,
        remaining_usd=max_usd - spent,
        blocked=bool(raw.get("blocked", False)),
        auth_id=str(raw.get("auth_id", "")),
        policy_version=POLICY_VERSION,
    )
    return snap


def verify_budget_feasibility(
    requirements: BudgetRequirements,
    auth: AuthSnapshot,
) -> str:
    """Compare plan demand to REMAINING authorization (max - consumed).

    Remaining semantics:
      remaining_requests = max_requests - consumed_requests
      remaining_tokens_* = max_tokens_* - consumed_tokens_*
      remaining_usd      = max_cost_usd - spent_usd

    If remaining fields are absent, fail closed (do not fall back to max).
    """
    if not isinstance(requirements, dict):
        return "BUDGET_REQ_TYPE"
    if not isinstance(auth, dict):
        return "BUDGET_AUTH_TYPE"
    if auth.get("blocked"):
        return "BUDGET_AUTH_BLOCKED"

    # Prefer explicit remaining_*; do NOT silently use max_* when remaining missing.
    for key in ("remaining_requests", "remaining_tokens_in", "remaining_tokens_out", "remaining_usd"):
        if key not in auth:
            return "BUDGET_REMAINING_MISSING:%s" % key

    try:
        need_req = int(requirements["requests_with_margin"])
        need_in = int(requirements["tokens_in_with_margin"])
        need_out = int(requirements["tokens_out_with_margin"])
        need_usd = float(requirements["usd_with_margin"])
        rem_req = int(auth["remaining_requests"])
        rem_in = int(auth["remaining_tokens_in"])
        rem_out = int(auth["remaining_tokens_out"])
        rem_usd = float(auth["remaining_usd"])
    except Exception:
        return "BUDGET_FIELDS_INVALID"

    if need_req < 0 or need_in < 0 or need_out < 0 or need_usd < 0:
        return "BUDGET_NEED_NEGATIVE"
    if rem_req < 0 or rem_in < 0 or rem_out < 0 or rem_usd < 0:
        return "BUDGET_REMAINING_NEGATIVE"

    if need_req > rem_req:
        return "BUDGET_REQUESTS_EXCEEDED:need=%d,remaining=%d" % (need_req, rem_req)
    if need_in > rem_in:
        return "BUDGET_TOKENS_IN_EXCEEDED:need=%d,remaining=%d" % (need_in, rem_in)
    if need_out > rem_out:
        return "BUDGET_TOKENS_OUT_EXCEEDED:need=%d,remaining=%d" % (need_out, rem_out)
    if need_usd > rem_usd + 1e-12:
        return "BUDGET_USD_EXCEEDED:need=%.6f,remaining=%.6f" % (need_usd, rem_usd)
    return ""


def canonical_config_sha256(config: Dict[str, Any]) -> str:
    body = {k: v for k, v in config.items() if k != "config_sha256"}
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_exec_freeze(*, baseline_commit: str, r_values: Sequence[int] = (6, 10)) -> Dict[str, Any]:
    plan_seed_of = lambda r: BASE_SEED + 1009 * r
    cfg: Dict[str, Any] = {
        "version": "R4-exec-v2-proposed",
        "status": "PROPOSED_PENDING_PLANNER_ACCEPTANCE",
        "supersedes": "R4-exec-v0-proposed and R4-exec-v1-proposed",
        "supersedes_reason": "v2 hardens budget policy in code (anti hash-recompute), remaining-quota checks, IUT F2, execution_authorized flag",
        "created_for": "LEVEL3-PILOT-R4 execution protocol (zero real model calls at freeze time)",
        "baseline_commit": baseline_commit,
        "parent_artefacts": {
            "graph_path": "results/level3_pilot_r2/frozen_candidates/parent_graph.py",
            "graph_sha256_byte": EXPECTED_PARENT_GRAPH_SHA,
            "graph_sha256_lf": EXPECTED_PARENT_LF_SHA,
            "prompt_path": "results/level3_pilot_r2/frozen_candidates/parent_prompt.py",
            "prompt_sha256": EXPECTED_PARENT_PROMPT_SHA,
        },
        "mutation_plan": {
            "seed_rule": "plan_seed[r] = BASE_SEED + 1009 * r",
            "base_seed": BASE_SEED,
            "operator_names": ["M_SET_INSTRUCTION", "M_ADD_SAMPLING"],
            "operator_probs": [0.5, 0.5],
            "instruction_pool": [
                "Solve step by step, end with 'Answer: <num>'.",
                "Think carefully, verify arithmetic, final number after 'Answer:'.",
                "Compute directly. Output the numeric answer after 'Answer:'.",
                "Solve briefly. Final answer after 'Answer:'.",
            ],
            "sampling_ks": [2, 3, 4],
            "allow_noop": False,
            "rng": "LCG (1664525, 1013904223, 2^32) keyed by (plan.seed + 10007*(slot+1))",
            "enabled_operators": ["M_SET_INSTRUCTION", "M_ADD_SAMPLING"],
            "disabled_operators": ["M_ADD_CHECK_STAGE", "M_SINGLE_EDIT"],
        },
        "seeds": {
            "base_seed": BASE_SEED,
            "r_values": list(r_values),
            "plan_seeds": {str(r): plan_seed_of(r) for r in r_values},
        },
        "pairing_blocks": {
            "description": "D and E share MutationPlan seed in block r; slots 0-1 from Parent; E slots 2-3 from gen-1 winner",
            "d_slots": [0, 1, 2, 3],
            "e_gen1_slots": [0, 1],
            "e_gen2_slots": [2, 3],
        },
        "operator_policy": {
            "failure_mode": "FailedCandidate retained at slot with dev_accuracy=0; never silent redraw",
            "noop": "NOOP_MUTATION becomes FailedCandidate",
            "specs_ref": "src/research/r4_workflow_program.OPERATOR_SPECS",
        },
        "selection_rules": {
            "gen1_winner": "max dev accuracy on shared dev set; ties -> creation order",
            "e_final": "max dev accuracy among 4 slots; ties -> creation order e1a<e1b<e2a<e2b",
            "d_final": "max dev accuracy among 4 slots; ties -> creation order",
            "failed_candidate_score": 0.0,
        },
        "datasets": {
            "confirmation": {
                "file": "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json",
                "task_set_sha256": EXPECTED_CONFIRM_V1_SHA,
                "n": 40,
                "role": "final scoring only; never selection",
            },
            "development": {
                "file": "results/level3_pilot_r4_data/gsm8k_train_official.jsonl",
                "sha256": EXPECTED_TRAIN_SHA,
                "n_available": 7473,
                "n_used": 20,
                "role": "candidate ranking only",
                "selection_rule": "first 20 official train indices (frozen before calls; not performance-based)",
            },
            "generation_tasks": {
                "required": False,
                "note": "R4 mutations are syntactic MutationPlan operators; no LLM rewrite generation set",
            },
        },
        "evaluation": {
            "scoring": "host-side gold; never in container/prompt/IPC",
            "answer_extract": "project extractor; exact match on canonical gold",
            "failure_scoring": {
                "invalid_output": "incorrect",
                "timeout": "incorrect",
                "execution_failure": "incorrect",
                "missing_row": "incorrect",
                "no_task_dropping": True,
            },
            "request_log_required": True,
        },
        "endpoints": {
            "primary": "co-primary seed-level paired E-D and E-C confirmation accuracy (IUT; conditional on frozen 40 tasks)",
            "secondary": [
                "task-level McNemar within block",
                "task-level Holm family F1",
                "cost/call/latency (RQ4)",
            ],
            "holm_family": ["B-A", "C-A", "D-A", "E-A", "E-D"],
            "holm_note": "F1 Holm(5) is TASK-level only. Seed-level RQ3 uses family F2 = {E-D, E-C} with Holm(2) if both are co-primary; see R4_R5_STATISTICAL_CONSISTENCY.md. R=6 unadj. min Wilcoxon p=0.03125 is NOT enough for Holm(5) step-1 (0.01).",
            "rq3_comparisons": {
                "E-D": {"role": "co-primary", "family": "F2", "test": "exact_wilcoxon_signed_rank_two_sided", "alpha": 0.05, "direction": "favor_E"},
                "E-C": {"role": "co-primary", "family": "F2", "test": "exact_wilcoxon_signed_rank_two_sided", "alpha": 0.05, "direction": "favor_E"},
                "multiplicity": "IUT",
                "claim_rule": "IUT: joint claim E beats BOTH D and C requires BOTH E-D and E-C to reject in favor of E at alpha=0.05; no Holm(2) on F2. Single-comparison confirmatory claims need separate pre-declared FWER control else exploratory only.",
            },
            "tests": {
                "task_level": "exact McNemar two-sided",
                "seed_level": "exact Wilcoxon signed-rank two-sided on paired d[r]",
            },
            "stopping": "fixed-N; no optional stopping",
        },
        "budget_caps": {
            "requests_formula": REQUESTS_FORMULA,
            "base_requests": 240,
            "per_r_requests": 240,
            "safety_margin": SAFETY_MARGIN,
            "token_in_per_req": [150, 400],
            "token_out_per_req": [150, 800],
            "worst_case_usd_per_req": WORST_USD_PER_REQ,
            "planned_r_values": list(r_values),
            "current_auth_caps_reference": {
                "max_requests": 300,
                "max_tokens_in": 2000000,
                "max_tokens_out": 200000,
                "max_cost_usd": 5.0,
                "note": "reference only; feasibility is computed against a live AuthSnapshot at verify time",
            },
            "authorization_required": True,
            "real_api_allowed_at_freeze_time": False,
            "budget_gate_is_fail_closed": True,
            "policy_version": POLICY_VERSION,
        },
        "execution_authorized": False,
    }
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    return cfg


DEFAULT_EXEC_FREEZE = build_exec_freeze(baseline_commit="ed1623a7fae56d6293fb05a71258b5d3747af7c5")


def verify_exec_config_structure(config: Dict[str, Any]) -> str:
    """Layer 1: structure + hash only. Does NOT imply budget sufficiency."""
    if not isinstance(config, dict):
        return "EXEC_CONFIG_NOT_OBJECT"
    for k in REQUIRED_KEYS:
        if k not in config:
            return "EXEC_FREEZE_MISSING_FIELD:%s" % k

    declared = config.get("config_sha256")
    recomputed = canonical_config_sha256(config)
    if declared != recomputed:
        return "EXEC_FREEZE_HASH_MISMATCH"

    pa = config.get("parent_artefacts") or {}
    if pa.get("graph_sha256_byte") != EXPECTED_PARENT_GRAPH_SHA:
        return "EXEC_PARENT_GRAPH_SHA"
    if pa.get("prompt_sha256") != EXPECTED_PARENT_PROMPT_SHA:
        return "EXEC_PARENT_PROMPT_SHA"

    mp = config.get("mutation_plan") or {}
    names = mp.get("operator_names") or []
    probs = mp.get("operator_probs") or []
    if not names or len(names) != len(probs):
        return "EXEC_PLAN_NAME_PROB_LEN"
    if any(not isinstance(p, (int, float)) or isinstance(p, bool) or p < 0 for p in probs):
        return "EXEC_PLAN_PROB_NEGATIVE"
    if abs(sum(probs) - 1.0) > 1e-6:
        return "EXEC_PLAN_PROB_SUM"
    if not mp.get("instruction_pool"):
        return "EXEC_PLAN_EMPTY_POOL"

    seeds = config.get("seeds") or {}
    if "base_seed" not in seeds or "plan_seeds" not in seeds:
        return "EXEC_SEEDS_INCOMPLETE"
    pss = list(seeds["plan_seeds"].values())
    if len(pss) != len(set(pss)):
        return "EXEC_SEEDS_NOT_UNIQUE"
    for r, s in seeds["plan_seeds"].items():
        try:
            expected = int(seeds["base_seed"]) + 1009 * int(r)
            if int(s) != expected:
                return "EXEC_SEEDS_RULE_MISMATCH:%s" % r
        except Exception:
            return "EXEC_SEEDS_RULE_INVALID:%s" % r

    sr = config.get("selection_rules") or {}
    if sr.get("failed_candidate_score") != 0.0:
        return "EXEC_SELECTION_FAILED_SCORE"

    ds = config.get("datasets") or {}
    if (ds.get("confirmation") or {}).get("task_set_sha256") != EXPECTED_CONFIRM_V1_SHA:
        return "EXEC_CONFIRM_SHA"
    if (ds.get("development") or {}).get("sha256") != EXPECTED_TRAIN_SHA:
        return "EXEC_DEV_SHA"

    bc = config.get("budget_caps") or {}
    if bc.get("real_api_allowed_at_freeze_time") is not False:
        return "EXEC_BUDGET_REAL_API_FLAG"
    if "requests_formula" not in bc:
        return "EXEC_BUDGET_FORMULA"

    # P0: budget numbers must match the VERSIONED POLICY — config_sha256 is
    # never sufficient to prove budget integrity.
    err = policy_mismatch(bc)
    if err:
        return err

    # planned_r_values must agree with seeds.r_values and plan_seeds keys
    planned = bc.get("planned_r_values")
    r_values = seeds.get("r_values") or []
    plan_keys = sorted((seeds.get("plan_seeds") or {}).keys(), key=lambda x: int(x))
    if not isinstance(planned, (list, tuple)) or not planned:
        return "BUDGET_PLANNED_R_INVALID"
    try:
        planned_ints = [int(x) for x in planned]
        r_ints = [int(x) for x in r_values]
        key_ints = [int(x) for x in plan_keys]
    except Exception:
        return "BUDGET_R_NOT_INT"
    if planned_ints != r_ints:
        return "BUDGET_PLANNED_R_NEQ_SEEDS"
    if sorted(planned_ints) != key_ints:
        return "BUDGET_PLANNED_R_NEQ_PLAN_SEEDS"

    ep = config.get("endpoints") or {}
    if "holm_family" not in ep or len(ep.get("holm_family") or []) != 5:
        return "EXEC_ENDPOINTS_HOLM_FAMILY"

    # F2 / IUT consistency with Planner decision (Task C)
    rq3 = ep.get("rq3_comparisons") or {}
    if "E-D" not in rq3 or "E-C" not in rq3:
        return "EXEC_ENDPOINTS_RQ3_MISSING_COMPARISON"
    for key in ("E-D", "E-C"):
        if (rq3.get(key) or {}).get("role") != "co-primary":
            return "EXEC_ENDPOINTS_RQ3_ROLE:%s" % key
    claim = (rq3.get("claim_rule") or "").lower()
    if "iut" not in claim and "both" not in claim:
        return "EXEC_ENDPOINTS_RQ3_CLAIM_RULE"

    # status must be PROPOSED-ish and execution_authorized must be false/absent
    status = str(config.get("status", ""))
    if status in HTTP_FORBIDDEN_STATUSES:
        pass  # expected for proposed freeze
    if config.get("execution_authorized") is True:
        return "EXEC_EXECUTION_AUTH_FLAG"

    return ""


def _requirements_from_config(config: Dict[str, Any], r: int) -> BudgetRequirements:
    bc = config.get("budget_caps") or {}
    try:
        return compute_budget_requirements(
            r,
            safety_margin=float(bc.get("safety_margin", SAFETY_MARGIN)),
            token_in_high=int(bc.get("token_in_per_req", [150, 400])[1]),
            token_out_high=int(bc.get("token_out_per_req", [150, 800])[1]),
            usd_per_req=float(bc.get("worst_case_usd_per_req", WORST_USD_PER_REQ)),
            base_requests=int(bc.get("base_requests", 240)),
            per_r_requests=int(bc.get("per_r_requests", 240)),
        )
    except BudgetError as exc:
        raise


def verify_exec_freeze(
    config: Dict[str, Any],
    *,
    auth: Optional[AuthSnapshot] = None,
    require_budget: bool = True,
) -> str:
    """Full fail-closed verification.

    * Always runs structure/hash checks.
    * If ``require_budget`` (default True), also loads/uses auth snapshot and
      rejects any planned R whose demand (incl. safety margin) exceeds caps.
    * Never creates or resets authorization state.
    """
    err = verify_exec_config_structure(config)
    if err:
        return err

    if not require_budget:
        return ""

    if auth is None:
        try:
            auth = load_auth_snapshot()
        except AuthError as exc:
            return "BUDGET_AUTH_UNAVAILABLE:%s" % (exc.args[0] if exc.args else type(exc).__name__)

    bc = config.get("budget_caps") or {}
    planned = bc.get("planned_r_values")
    if not planned:
        return "BUDGET_PLANNED_R_MISSING"
    if not isinstance(planned, (list, tuple)) or not planned:
        return "BUDGET_PLANNED_R_INVALID"

    for r in planned:
        try:
            req = _requirements_from_config(config, int(r))
        except BudgetError as exc:
            return "BUDGET_REQ_INVALID:R=%s:%s" % (r, exc.args[0] if exc.args else "")
        err = verify_budget_feasibility(req, auth)
        if err:
            return err
    return ""


def verify_execution_allowed(
    config: Dict[str, Any],
    *,
    auth: Optional[AuthSnapshot] = None,
    execution_authorized: bool = False,
) -> str:
    """Gate BEFORE any HTTP. Budget/config success never implies authorization.

    Returns '' only when:
      * config status is not a forbidden/PROPOSED status, AND
      * explicit execution_authorized flag is True, AND
      * auth snapshot is present, not blocked, and remaining budget is sufficient
        for the plan (re-checked here).

    Otherwise a stable error code. Never mutates auth.
    """
    status = str((config or {}).get("status", ""))
    if status in HTTP_FORBIDDEN_STATUSES or not status:
        return "EXEC_STATUS_BLOCKS_HTTP:status=%s" % status
    if not execution_authorized:
        return "EXEC_NOT_AUTHORIZED_BY_PLANNER"
    if (config or {}).get("execution_authorized") is not True:
        return "EXEC_CONFIG_AUTH_FLAG"
    if auth is None:
        try:
            auth = load_auth_snapshot()
        except AuthError as exc:
            return "BUDGET_AUTH_UNAVAILABLE:%s" % (exc.args[0] if exc.args else "")
    if auth.get("blocked"):
        return "BUDGET_AUTH_BLOCKED"
    # re-check budget vs remaining
    bc = config.get("budget_caps") or {}
    planned = bc.get("planned_r_values") or []
    for r in planned:
        try:
            req = _requirements_from_config(config, int(r))
        except Exception as exc:
            return "BUDGET_REQ_INVALID:%s" % exc
        err = verify_budget_feasibility(req, auth)
        if err:
            return err
    return ""
