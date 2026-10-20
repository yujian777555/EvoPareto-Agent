"""Offline seed audit for D/E mutation mechanism (zero API requests).

For BASE_SEED=20260601 and planned R in {6, 10}, generate D flat and E
two-generation candidates under the default MutationPlan and record every
slot: block, seed, group, generation, slot, parent id, operator, params,
before/after representation hash, success, failure reason, and a
deterministic re-run check.

Usage:
    python scripts/level3_pilot_r4/audit_mutation_seeds.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_workflow_program import (
    FailedCandidate,
    WorkflowProgram,
    apply_mutation,
    default_mutation_plan,
    generate_flat_candidates,
    generate_two_generation_candidates,
    load_frozen_parent,
    program_provenance,
)

BASE_SEED = 20260601
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
OUT = ROOT / "docs" / "level3_pilot_r4_design/mutation_seed_audit.json"


def _rec(stage: str, program: WorkflowProgram, **extra: Any) -> Dict[str, Any]:
    prov = program_provenance(program)
    row = {
        "status": "SUCCESS",
        "program_id": program.program_id,
        "parent_program_id": program.parent_program_id,
        "generation": program.generation,
        "operator_history": list(program.operator_history),
        "graph_sha256": prov["graph_sha256"],
        "instruction_sha256": prov["instruction_sha256"],
        "call_style": program.call_style,
        "n_samples": program.n_samples,
        "aggregation": program.aggregation,
    }
    row.update(extra)
    return row


def _rec_fail(fail: FailedCandidate, **extra: Any) -> Dict[str, Any]:
    row = {
        "status": "FAILED",
        "slot": fail.slot,
        "operator": fail.operator,
        "reason": fail.reason,
        "parent_program_id": fail.parent_program_id,
        "generation": fail.generation,
        "dev_accuracy": 0.0,
    }
    row.update(extra)
    return row


def audit_seeds() -> Dict[str, Any]:
    parent = load_frozen_parent(FROZEN)
    rows: List[Dict[str, Any]] = []
    summary = {
        "n_blocks": 0,
        "n_d_success": 0,
        "n_d_failed": 0,
        "n_e_gen1_success": 0,
        "n_e_gen1_failed": 0,
        "n_e_gen2_success": 0,
        "n_e_gen2_failed": 0,
        "n_e_gen2_consecutive_fail_blocks": 0,
    }

    for R in (6, 10):
        for r in range(1, R + 1):
            plan_seed = BASE_SEED + 1009 * r
            plan = default_mutation_plan(plan_seed)
            summary["n_blocks"] += 1

            # --- Group D ---
            def mut_d(p, i, _plan=plan):
                return apply_mutation(p, _plan, slot=i)

            d_cands = generate_flat_candidates(parent, n_candidates=4, mutator=mut_d)
            for i, c in enumerate(d_cands):
                extra = {"R": R, "block": r, "plan_seed": plan_seed, "group": "D", "slot": i, "kind": "D"}
                if isinstance(c, FailedCandidate):
                    summary["n_d_failed"] += 1
                    rows.append(_rec_fail(c, **extra))
                else:
                    summary["n_d_success"] += 1
                    rows.append(_rec("D", c, **extra))

            # --- Group E ---
            def mut_e(p, i, _plan=plan):
                return apply_mutation(p, _plan, slot=i)

            # gen1 scores: use instruction-hash pseudo score for selection only
            def score_fn(c: WorkflowProgram) -> float:
                # deterministic pseudo dev score from graph sha (offline only)
                h = int(program_provenance(c)["graph_sha256"][:8], 16)
                return (h % 1000) / 1000.0

            g1, winner, g2 = generate_two_generation_candidates(
                parent, mutator=mut_e, dev_scores_gen1=score_fn
            )
            for i, c in enumerate(g1):
                extra = {"R": R, "block": r, "plan_seed": plan_seed, "group": "E", "slot": i, "kind": "E_GEN1"}
                if isinstance(c, FailedCandidate):
                    summary["n_e_gen1_failed"] += 1
                    rows.append(_rec_fail(c, **extra))
                else:
                    summary["n_e_gen1_success"] += 1
                    rows.append(_rec("E_GEN1", c, **extra))

            if isinstance(winner, FailedCandidate):
                rows.append(_rec_fail(winner, R=R, block=r, plan_seed=plan_seed, group="E", slot="winner", kind="E_WINNER"))
            else:
                rows.append(_rec("E_WINNER", winner, R=R, block=r, plan_seed=plan_seed, group="E", slot="winner"))

            gen2_fail_run = 0
            for i, c in enumerate(g2):
                extra = {"R": R, "block": r, "plan_seed": plan_seed, "group": "E", "slot": i + 2, "kind": "E_GEN2"}
                if isinstance(c, FailedCandidate):
                    summary["n_e_gen2_failed"] += 1
                    gen2_fail_run += 1
                    rows.append(_rec_fail(c, **extra))
                else:
                    summary["n_e_gen2_success"] += 1
                    rows.append(_rec("E_GEN2", c, **extra))
            if gen2_fail_run == 2:
                summary["n_e_gen2_consecutive_fail_blocks"] += 1

    # deterministic re-run check (first block only, cheap)
    plan = default_mutation_plan(BASE_SEED + 1009 * 1)
    a = apply_mutation(parent, plan, slot=0)
    b = apply_mutation(parent, plan, slot=0)
    same = True
    if isinstance(a, WorkflowProgram) and isinstance(b, WorkflowProgram):
        same = (
            a.graph_source == b.graph_source
            and a.instruction == b.instruction
            and a.operator_history == b.operator_history
        )
    elif isinstance(a, FailedCandidate) and isinstance(b, FailedCandidate):
        same = a.reason == b.reason and a.operator == b.operator
    else:
        same = False

    return {
        "evidence_class": "OFFLINE_SEED_AUDIT_NO_API",
        "base_seed": BASE_SEED,
        "R_values": [6, 10],
        "plan": default_mutation_plan(BASE_SEED + 1009).to_dict(),
        "summary": summary,
        "deterministic_rerun_slot0_block1": same,
        "rows": rows,
    }


def main() -> int:
    report = audit_seeds()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", OUT)
    print("summary", json.dumps(report["summary"], sort_keys=True))
    print("deterministic", report["deterministic_rerun_slot0_block1"])
    print("n_rows", len(report["rows"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
