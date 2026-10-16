"""Stage 2.0-R1 frozen multi-seed experiment (no real API)."""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.fceol_r1.evaluator import operator_learning_protocol, oracle_upper_bound
from src.research.fceol_r1.policies import (
    FCEOL,
    FixedMap,
    GlobalAOS,
    RandomPolicy,
    ShuffledEvidencePolicy,
    ContextualUCB,
)
from src.research.fceol_r1.task_suite import (
    audit_splits,
    make_task_suite,
    split_by_template,
)

OUT = ROOT / "results/stage2_0_r1"
SEEDS = list(range(10))  # 10 seeds


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _ci95(xs):
    if len(xs) < 2:
        return 0.0
    return 1.96 * _std(xs) / math.sqrt(len(xs))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = make_task_suite(n_per_fault=6, seed=11)
    train, dev, test = split_by_template(tasks, seed=7)
    audit = audit_splits(tasks, train, dev, test)
    (OUT / "split_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (OUT / "task_manifest.json").write_text(json.dumps({
        "total": len(tasks),
        "unique_keys": [t.unique_key() for t in tasks],
        "templates": sorted({t.template_id for t in tasks}),
    }, indent=2), encoding="utf-8")
    (OUT / "preregistration.json").write_text(json.dumps({
        "frozen": True,
        "seeds": SEEDS,
        "primary_metric": "frozen_transfer mean_final_reward on heldout",
        "secondary": ["task_success_rate", "mean_paired_delta", "improvement_prob", "negative_rate"],
        "controls": ["random", "global_aos", "fixed_map", "contextual_bandit",
                     "fceol", "shuffled", "unknown_only", "wrong_diagnosis", "oracle"],
        "protocols": ["frozen_transfer", "online_adaptation"],
        "real_llm_calls": 0,
    }, indent=2), encoding="utf-8")

    def policies():
        return {
            "random": RandomPolicy(),
            "global_aos": GlobalAOS(),
            "fixed_map": FixedMap(),
            "contextual_bandit": ContextualUCB(),
            "fceol": FCEOL(),
            "shuffled": ShuffledEvidencePolicy(),
        }

    # ---- Protocol A: frozen transfer on heldout ----
    frozen: Dict[str, List[float]] = {k: [] for k in
        ["random", "global_aos", "fixed_map", "contextual_bandit", "fceol", "shuffled",
         "unknown_only", "wrong_diagnosis"]}
    frozen_succ = {k: [] for k in frozen}
    frozen_delta = {k: [] for k in frozen}

    for sd in SEEDS:
        # train FCEOL-family policies on train split, then freeze
        for name in ["global_aos", "fixed_map", "contextual_bandit", "fceol", "shuffled"]:
            pol = policies()[name]
            ev_mode = "SHUFFLED_EVIDENCE" if name == "shuffled" else "TRUE_EVIDENCE"
            operator_learning_protocol(pol, train, seed=sd, steps_per_task=3,
                                       evidence_mode=ev_mode, freeze_policy=False)
            res = operator_learning_protocol(pol, test, seed=sd + 100, steps_per_task=3,
                                             evidence_mode=ev_mode, freeze_policy=True)
            frozen[name].append(res["mean_final_reward"])
            frozen_succ[name].append(res["task_success_rate"])
            frozen_delta[name].append(res["mean_paired_delta"])
        # baselines without training
        res = operator_learning_protocol(RandomPolicy(), test, seed=sd + 100, steps_per_task=3, freeze_policy=True)
        frozen["random"].append(res["mean_final_reward"])
        frozen_succ["random"].append(res["task_success_rate"])
        frozen_delta["random"].append(res["mean_paired_delta"])

        from src.research.fceol_r1.evidence import build_evidence
        # unknown-only / wrong-diagnosis as evidence modes on frozen FCEOL
        for mode, key in (("UNKNOWN_ONLY", "unknown_only"), ("WRONG_DIAGNOSIS", "wrong_diagnosis")):
            pol = FCEOL()
            operator_learning_protocol(pol, train, seed=sd, steps_per_task=3,
                                       evidence_mode="TRUE_EVIDENCE", freeze_policy=False)
            res = operator_learning_protocol(pol, test, seed=sd + 100, steps_per_task=3,
                                             evidence_mode=mode, freeze_policy=True)
            frozen[key].append(res["mean_final_reward"])
            frozen_succ[key].append(res["task_success_rate"])
            frozen_delta[key].append(res["mean_paired_delta"])

    # ---- Protocol B: online adaptation on heldout ----
    online: Dict[str, List[float]] = {"fceol": [], "global_aos": [], "random": []}
    for sd in SEEDS:
        pol = FCEOL()
        res = operator_learning_protocol(pol, test, seed=sd + 200, steps_per_task=3,
                                         evidence_mode="TRUE_EVIDENCE", freeze_policy=False)
        online["fceol"].append(res["mean_final_reward"])
        pol = GlobalAOS()
        res = operator_learning_protocol(pol, test, seed=sd + 200, steps_per_task=3,
                                         evidence_mode="TRUE_EVIDENCE", freeze_policy=False)
        online["global_aos"].append(res["mean_final_reward"])
        res = operator_learning_protocol(RandomPolicy(), test, seed=sd + 200, steps_per_task=3,
                                         evidence_mode="TRUE_EVIDENCE", freeze_policy=False)
        online["random"].append(res["mean_final_reward"])

    # oracle upper bound (exact enumeration, 3-step budget)
    oracle = oracle_upper_bound(test, budget=3)

    def summarize(d):
        return {k: {"mean": _mean(v), "std": _std(v), "ci95": _ci95(v), "n": len(v)}
                for k, v in d.items()}

    frozen_summary = {
        "mean_final_reward": summarize(frozen),
        "task_success_rate": summarize(frozen_succ),
        "mean_paired_delta": summarize(frozen_delta),
        "oracle_mean_best_reward": oracle["mean_best_reward"],
    }
    (OUT / "frozen_transfer_results.json").write_text(json.dumps(frozen_summary, indent=2), encoding="utf-8")
    (OUT / "oracle_validation.json").write_text(json.dumps(oracle, indent=2), encoding="utf-8")
    (OUT / "online_adaptation_results.json").write_text(json.dumps({
        "mean_final_reward": summarize(online),
        "note": "Protocol B — online updates allowed; separate from frozen transfer",
    }, indent=2), encoding="utf-8")

    # paired diffs fceol vs global_aos
    diffs = [a - b for a, b in zip(frozen["fceol"], frozen["global_aos"])]
    (OUT / "multiseed_summary.json").write_text(json.dumps({
        "seeds": SEEDS,
        "fceol_minus_global_aos": {"mean": _mean(diffs), "std": _std(diffs), "ci95": _ci95(diffs)},
        "fceol_minus_shuffled": {"mean": _mean([a - b for a, b in zip(frozen["fceol"], frozen["shuffled"])])},
        "fceol_minus_random": {"mean": _mean([a - b for a, b in zip(frozen["fceol"], frozen["random"])])},
        "fceol_minus_contextual_bandit": {"mean": _mean([a - b for a, b in zip(frozen["fceol"], frozen["contextual_bandit"])])},
        "per_seed_fceol": frozen["fceol"],
        "per_seed_global_aos": frozen["global_aos"],
    }, indent=2), encoding="utf-8")

    (OUT / "negative_results.json").write_text(json.dumps({
        "note": "negative or null findings preserved",
        "cases": [
            "if fceol <= global_aos, report honestly",
            "if shuffled ~= fceol, failure conditioning adds nothing",
            "if wrong_diagnosis >= fceol, diagnosis quality not critical",
        ],
    }, indent=2), encoding="utf-8")

    print(json.dumps(frozen_summary, indent=2))
    print("oracle", oracle["mean_best_reward"])
    print("fceol-vs-aos", _mean(diffs), "±", _ci95(diffs))


if __name__ == "__main__":
    main()
