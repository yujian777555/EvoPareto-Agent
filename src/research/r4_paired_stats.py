"""Offline paired-comparison statistics for LEVEL3-PILOT-R4.

This module is intentionally model-free: it never imports HTTP clients, never
reads credentials, and never calls any provider. All inputs are plain dicts or
path-like objects supplied by the caller. Simulated inputs must be tagged by
the caller as evidence_class=SIMULATED; this module only reports that tag.

Canonical task-set serialization (R4-RF freeze):
  * tasks sorted by ``task_id`` ascending (lexicographic, code-point order)
  * each task contributes a 3-element JSON array: [task_id, question, gold_answer]
  * outer structure is a JSON array of those arrays
  * json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=False)
  * encoded as UTF-8 (no BOM), SHA-256 hex digest lowercase
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "CANONICAL_TASKSET_JSON_KWARGS",
    "PairedCounts",
    "PairedComparison",
    "count_paired",
    "exact_mcnemar",
    "wilson_ci",
    "holm_bonferroni",
    "detect_anomalies",
    "canonical_task_set_sha256",
    "canonical_task_set_blob",
    "verify_task_set",
    "check_frozen_unchanged",
    "check_budget_consistency",
    "summarize_groups",
]

#: Frozen JSON kwargs for task-set hashing. Changing these voids all SHAs.
CANONICAL_TASKSET_JSON_KWARGS = {
    "ensure_ascii": False,
    "separators": (",", ":"),
    "sort_keys": False,
}


# ---------------------------------------------------------------------------
# Paired counts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PairedCounts:
    """2x2 paired table for one comparator X vs baseline A."""

    b: int  # X correct, A wrong   (improved)
    c: int  # X wrong,  A correct  (regressed)
    n11: int
    n00: int

    @property
    def n(self) -> int:
        return self.b + self.c + self.n11 + self.n00

    @property
    def discordant(self) -> int:
        return self.b + self.c

    @property
    def net_gain(self) -> int:
        return self.b - self.c

    def as_dict(self) -> Dict[str, int]:
        return {
            "b_improved": self.b,
            "c_regressed": self.c,
            "n11_both_correct": self.n11,
            "n00_both_wrong": self.n00,
            "n": self.n,
            "discordant_pairs": self.discordant,
            "net_gain": self.net_gain,
        }


def _strict_bool(value: Any, *, task_id: str, allow_int_01: bool) -> bool:
    """Coerce a scored result to bool without silent conversion.

    Only ``bool`` is accepted by default. Integers 0/1 are accepted only when
    ``allow_int_01=True``. Strings ("false", "true", "0"), None, and floats
    always raise — they must never be treated as correct/incorrect.
    """
    if isinstance(value, bool):
        return value
    if allow_int_01 and isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    raise TypeError(
        f"SCORE_TYPE_INVALID task_id={task_id!r} value={value!r} type={type(value).__name__}; "
        "only bool (or int 0/1 when allow_int_01=True) is allowed"
    )


def count_paired(
    baseline: Mapping[str, Any],
    comparator: Mapping[str, Any],
    *,
    ids: Optional[Sequence[str]] = None,
    allow_int_01: bool = False,
) -> PairedCounts:
    """Build paired counts from {task_id: correct} maps.

    Strict rules:
      * result values must be bool (or int 0/1 only if allow_int_01=True)
      * missing IDs raise; they are never treated as incorrect and never dropped
      * duplicate IDs in the explicit ``ids`` list raise
      * ID set mismatch between the two maps raises
    """
    if ids is not None:
        id_list = [str(i) for i in ids]
        if len(id_list) != len(set(id_list)):
            seen = set()
            dups = []
            for i in id_list:
                if i in seen:
                    dups.append(i)
                seen.add(i)
            raise ValueError(f"duplicate task ids in explicit id list: {sorted(set(dups))[:5]}")
        for tid in id_list:
            if tid not in baseline:
                raise ValueError(f"missing task id in baseline: {tid}")
            if tid not in comparator:
                raise ValueError(f"missing task id in comparator: {tid}")
        keys = id_list
    else:
        keys_a = set(baseline)
        keys_b = set(comparator)
        if keys_a != keys_b:
            missing_a = sorted(keys_b - keys_a)
            missing_b = sorted(keys_a - keys_b)
            raise ValueError(
                f"id set mismatch: only_in_comparator={missing_a[:5]} "
                f"only_in_baseline={missing_b[:5]}"
            )
        if not keys_a:
            raise ValueError("empty task id set")
        keys = sorted(keys_a)

    b = c = n11 = n00 = 0
    for tid in keys:
        a = _strict_bool(baseline[tid], task_id=f"baseline:{tid}", allow_int_01=allow_int_01)
        x = _strict_bool(comparator[tid], task_id=f"comparator:{tid}", allow_int_01=allow_int_01)
        if x and not a:
            b += 1
        elif a and not x:
            c += 1
        elif a and x:
            n11 += 1
        else:
            n00 += 1
    return PairedCounts(b=b, c=c, n11=n11, n00=n00)



# ---------------------------------------------------------------------------
# Exact McNemar
# ---------------------------------------------------------------------------

def _binom_pmf(n: int, k: int, p: float = 0.5) -> float:
    if k < 0 or k > n:
        return 0.0
    return math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))


def exact_mcnemar(
    b: int,
    c: int,
    *,
    direction: str = "comparator_better",
) -> Dict[str, Any]:
    """Exact McNemar test on discordant counts (b, c).

    Cell meaning is fixed:
      * ``b``: comparator correct, baseline wrong  (comparator wins)
      * ``c``: comparator wrong,  baseline correct (baseline wins)

    ``direction`` declares the one-sided alternative and must be set before
    seeing results (default: comparator_better). It cannot be chosen to match
    the observed sign of (b-c).

    * ``comparator_better``: p_one_sided = P[X >= b], X ~ Bin(b+c, 0.5)
    * ``baseline_better``:   p_one_sided = P[X >= c]

    The confirmatory value for R4 is ``p_two_sided``.
    """
    if not isinstance(b, int) or isinstance(b, bool) or not isinstance(c, int) or isinstance(c, bool):
        raise TypeError("b and c must be int (not bool)")
    if b < 0 or c < 0:
        raise ValueError("b and c must be non-negative")
    if direction not in ("comparator_better", "baseline_better"):
        raise ValueError("direction must be 'comparator_better' or 'baseline_better'")

    n = b + c
    if n == 0:
        return {
            "n_discordant": 0,
            "p_one_sided": 1.0,
            "p_two_sided": 1.0,
            "direction": direction,
            "note": "no discordant pairs",
        }

    k_min = min(b, c)
    k_max = max(b, c)
    p_low = sum(_binom_pmf(n, k, 0.5) for k in range(0, k_min + 1))
    p_high = sum(_binom_pmf(n, k, 0.5) for k in range(k_max, n + 1))
    p_two = min(1.0, 2.0 * min(p_low, p_high))

    if direction == "comparator_better":
        # P[X >= b]
        p_one = sum(_binom_pmf(n, k, 0.5) for k in range(b, n + 1))
    else:
        # P[X >= c]
        p_one = sum(_binom_pmf(n, k, 0.5) for k in range(c, n + 1))

    return {
        "n_discordant": n,
        "p_one_sided": p_one,
        "p_two_sided": p_two,
        "direction": direction,
        "b": b,
        "c": c,
        "cohen_g": (b / n) if n else 0.0,
    }



# ---------------------------------------------------------------------------
# Wilson CI for a single proportion
# ---------------------------------------------------------------------------

def wilson_ci(successes: int, total: int, z: float = 1.959963984540054) -> Tuple[float, float, float]:
    """Return (p_hat, low, high) Wilson score 95% CI for a binomial proportion."""
    if total <= 0:
        raise ValueError("total must be positive")
    if successes < 0 or successes > total:
        raise ValueError("successes out of range")
    phat = successes / total
    denom = 1.0 + z * z / total
    centre = phat + z * z / (2.0 * total)
    half = z * math.sqrt((phat * (1.0 - phat) / total) + (z * z / (4.0 * total * total)))
    low = (centre - half) / denom
    high = (centre + half) / denom
    return phat, max(0.0, low), min(1.0, high)


# ---------------------------------------------------------------------------
# Holm-Bonferroni
# ---------------------------------------------------------------------------

def holm_bonferroni(p_values: Mapping[str, float], alpha: float = 0.05) -> Dict[str, Dict[str, float]]:
    """Holm step-down adjusted p-values and reject decisions."""
    if not p_values:
        return {}
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0,1)")
    items = sorted(p_values.items(), key=lambda kv: (kv[1], kv[0]))
    m = len(items)
    out: Dict[str, Dict[str, float]] = {}
    running_max = 0.0
    for i, (name, p) in enumerate(items):
        adjusted_raw = (m - i) * p
        running_max = max(running_max, adjusted_raw)
        adj = min(1.0, running_max)
        out[name] = {
            "p_raw": p,
            "p_holm": adj,
            "reject": bool(adj <= alpha),
            "rank": i + 1,
        }
    return out


# ---------------------------------------------------------------------------
# Anomalies: duplicates, missing rows
# ---------------------------------------------------------------------------

def detect_anomalies(
    rows: Sequence[Mapping[str, Any]],
    *,
    required_ids: Sequence[str],
    id_key: str = "task_id",
    group_key: str = "role",
    expect_groups: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Detect duplicate IDs, missing IDs, and unexpected groups.

    ``rows`` is a flat list of per-task records (e.g. one row per task per group).
    """
    seen: Dict[Tuple[str, str], int] = {}
    duplicates: List[Dict[str, Any]] = []
    present_ids = set()
    groups_found = set()

    for i, row in enumerate(rows):
        tid = row.get(id_key)
        grp = row.get(group_key)
        if tid is None or grp is None:
            duplicates.append({"index": i, "reason": "missing id or group field"})
            continue
        groups_found.add(str(grp))
        key = (str(grp), str(tid))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            duplicates.append({"group": grp, "task_id": tid, "count": seen[key]})
        present_ids.add(str(tid))

    required = [str(x) for x in required_ids]
    missing_per_group: Dict[str, List[str]] = {}
    if expect_groups:
        for g in expect_groups:
            g_ids = {tid for (grp, tid), n in seen.items() if grp == g}
            miss = [t for t in required if t not in g_ids]
            if miss:
                missing_per_group[g] = miss

    missing_any = [t for t in required if t not in present_ids]

    return {
        "duplicate_rows": duplicates,
        "n_rows": len(rows),
        "n_unique_ids": len(present_ids),
        "missing_ids_any_group": missing_any,
        "missing_ids_per_group": missing_per_group,
        "groups_found": sorted(groups_found),
        "ok": (not duplicates) and (not missing_any) and (not missing_per_group),
    }


# ---------------------------------------------------------------------------
# Task-set hashing / verification
# ---------------------------------------------------------------------------

def canonical_task_set_blob(tasks: Sequence[Mapping[str, Any]]) -> bytes:
    """Canonical UTF-8 bytes for a task list.

    Rules (frozen):
      1. sort tasks by task_id ascending (str order)
      2. each task -> [task_id, question, gold_answer] as a JSON array
      3. outer JSON array of those arrays
      4. json.dumps with CANONICAL_TASKSET_JSON_KWARGS
         (ensure_ascii=False, separators=(",", ":"), sort_keys=False)
      5. encode utf-8
    """
    ordered = sorted(
        ((t["task_id"], t["question"], t["gold_answer"]) for t in tasks),
        key=lambda x: x[0],
    )
    payload = [[tid, q, g] for tid, q, g in ordered]
    return json.dumps(payload, **CANONICAL_TASKSET_JSON_KWARGS).encode("utf-8")


def canonical_task_set_sha256(tasks: Sequence[Mapping[str, Any]]) -> str:
    """Canonical SHA-256 hex digest of a frozen task list (see blob rules)."""
    return hashlib.sha256(canonical_task_set_blob(tasks)).hexdigest()


def verify_task_set(
    tasks: Sequence[Mapping[str, Any]],
    declared_hash: Optional[str],
    expected_hash: str,
    *,
    expected_count: Optional[int] = None,
) -> str:
    """Gate-style verification. Returns '' on success, else an error code.

    Order (mirrors run_paired_35.verify_taskset):
      FIELD_COMPLETENESS -> FIELD_TYPE -> ID_UNIQUENESS -> COUNT
      -> RECOMPUTED_VS_DECLARED -> DECLARED_VS_EXPECTED

    ``expected_count`` (when not None) is an explicit size gate. A change in
    task count is therefore rejected even before hash comparison. Passing
    ``expected_count=None`` restores hash-only checking (legacy callers).
    """
    required = ("task_id", "question", "gold_answer")
    for t in tasks:
        for k in required:
            v = t.get(k)
            if v is None or v == "":
                return f"TASKSET_FIELD_MISSING:{k}"
            if not isinstance(v, str):
                return f"TASKSET_FIELD_NOT_STR:{k}"

    ids = [t["task_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        return "TASKSET_DUPLICATE_ID"

    if not tasks:
        return "TASKSET_EMPTY"

    if expected_count is not None:
        if not isinstance(expected_count, int) or isinstance(expected_count, bool):
            return "TASKSET_EXPECTED_COUNT_NOT_INT"
        if expected_count < 0:
            return "TASKSET_EXPECTED_COUNT_NEGATIVE"
        if len(tasks) != expected_count:
            return f"TASKSET_COUNT_MISMATCH:got={len(tasks)} expected={expected_count}"

    recomputed = canonical_task_set_sha256(tasks)
    if declared_hash is None or declared_hash == "":
        return "TASKSET_DECLARED_HASH_MISSING"
    if recomputed != declared_hash:
        return "TASKSET_HASH_MISMATCH"
    if declared_hash != expected_hash:
        return "TASKSET_HASH_NOT_EXPECTED"
    return ""



# ---------------------------------------------------------------------------
# Frozen-results immutability
# ---------------------------------------------------------------------------

def check_frozen_unchanged(
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> Dict[str, Any]:
    """Compare two {relpath: sha256} snapshots of tracked results files."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "ok": not (added or removed or modified),
    }


# ---------------------------------------------------------------------------
# Budget consistency
# ---------------------------------------------------------------------------

def check_budget_consistency(
    *,
    planned_requests: int,
    remaining_requests: int,
    planned_cost_usd: float,
    remaining_cost_usd: float,
    planned_tokens_in: int,
    planned_tokens_out: int,
    cap_tokens_in: int,
    cap_tokens_out: int,
    new_requests_this_round: int = 0,
) -> Dict[str, Any]:
    """Fail-closed consistency checks for the R4 budget plan."""
    problems: List[str] = []
    if new_requests_this_round != 0:
        problems.append(f"NEW_REQUESTS_NONZERO:{new_requests_this_round}")
    if planned_requests < 0 or remaining_requests < 0:
        problems.append("NEGATIVE_REQUEST_COUNT")
    if planned_cost_usd < 0 or remaining_cost_usd < 0:
        problems.append("NEGATIVE_COST")
    if planned_tokens_in < 0 or planned_tokens_out < 0:
        problems.append("NEGATIVE_TOKENS")

    gap_requests = planned_requests - remaining_requests
    gap_cost = planned_cost_usd - remaining_cost_usd

    if planned_tokens_out > cap_tokens_out:
        problems.append(f"TOKEN_OUT_CAP_EXCEEDED:{planned_tokens_out}>{cap_tokens_out}")
    if planned_tokens_in > cap_tokens_in:
        problems.append(f"TOKEN_IN_CAP_EXCEEDED:{planned_tokens_in}>{cap_tokens_in}")

    fits_requests = planned_requests <= remaining_requests
    fits_cost = planned_cost_usd <= remaining_cost_usd

    return {
        "ok": not problems and fits_requests and fits_cost,
        "problems": problems,
        "fits_requests": fits_requests,
        "fits_cost": fits_cost,
        "gap_requests": gap_requests,
        "gap_cost_usd": gap_cost,
        "new_requests_this_round": new_requests_this_round,
    }


# ---------------------------------------------------------------------------
# Group summary
# ---------------------------------------------------------------------------

@dataclass
class PairedComparison:
    name: str
    counts: PairedCounts
    mcnemar: Dict[str, float] = field(default_factory=dict)
    accuracy_comparator: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    accuracy_baseline: Tuple[float, float, float] = (0.0, 0.0, 0.0)


def summarize_groups(
    baseline_name: str,
    baseline: Mapping[str, bool],
    comparators: Mapping[str, Mapping[str, bool]],
    *,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """Paired comparisons of each comparator vs baseline, with Holm correction."""
    n = len(baseline)
    if n == 0:
        raise ValueError("empty baseline")
    n_correct_base = sum(1 for v in baseline.values() if v)
    acc_base = wilson_ci(n_correct_base, n)

    comparisons: Dict[str, Any] = {}
    raw_p: Dict[str, float] = {}
    for name, comp in comparators.items():
        counts = count_paired(baseline, comp)
        mcn = exact_mcnemar(counts.b, counts.c, direction="comparator_better")
        n_correct = sum(1 for v in comp.values() if v)
        acc = wilson_ci(n_correct, len(comp))
        comparisons[name] = {
            "counts": counts.as_dict(),
            "mcnemar": mcn,
            "accuracy_comparator": {"p": acc[0], "ci95_low": acc[1], "ci95_high": acc[2]},
        }
        raw_p[name] = mcn["p_two_sided"]

    holm = holm_bonferroni(raw_p, alpha=alpha)
    for name, adj in holm.items():
        comparisons[name]["holm"] = adj

    return {
        "baseline": baseline_name,
        "n_tasks": n,
        "accuracy_baseline": {
            "p": acc_base[0],
            "ci95_low": acc_base[1],
            "ci95_high": acc_base[2],
            "correct": n_correct_base,
        },
        "comparisons": comparisons,
        "multiplicity_family": sorted(raw_p.keys()),
        "alpha": alpha,
        "evidence_class_note": "caller must tag SIMULATED vs REAL; this function does not fabricate either",
    }

