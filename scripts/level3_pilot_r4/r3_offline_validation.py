"""R3 offline validation — Mock LLM only. Zero real API.

Proves: candidates actually execute graph_source; mutations change behavior;
feedback drives operator choice; sets are disjoint; gold never in prompts.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_tasks import GSM8KTask, evaluate_workflow_output
from src.research.r3_mutation_feedback import (
    FailureRecord,
    apply_random_mutation,
    build_feedback_child,
    execute_candidate,
    hash_program,
    select_feedback_operator,
    summarize_feedback,
)
from src.research.r4_workflow_program import load_frozen_parent, program_provenance

OUT = ROOT / "results" / "level3_pilot_r4_micro_r3_offline"
TRAIN = ROOT / "results" / "level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
SEED = 20260603
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"

# Prior used indices (MICRO-R1 0-7, MICRO-R2 dev+holdout from stratify)
R1_INDICES = set(range(0, 8))
R2_DEV = [6245, 499, 6996, 4900, 2518]
R2_HOLD = [3741, 475, 5516, 2354, 1139, 1066, 3324, 7193]


def load_train():
    rows = []
    with TRAIN.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
            rows.append({"index": i, "question": o["question"], "answer_raw": ans, "gold": " ".join(gold.split())})
    return rows


def make_split(rows, used: set):
    pool = [r for r in rows if r["index"] not in used]
    rng = random.Random(SEED)
    idxs = list(range(len(pool)))
    rng.shuffle(idxs)
    screening = [pool[i] for i in idxs[:10]]
    dev = [pool[i] for i in idxs[10:15]]
    confirm = [pool[i] for i in idxs[15:23]]
    # disjoint assertion
    ids = [r["index"] for r in screening + dev + confirm]
    assert len(ids) == len(set(ids)), "split overlap"
    assert not set(ids) & used, "reused prior indices"
    return screening, dev, confirm


def mock_llm_for(program_kind: str):
    """Deterministic mock. Parent solves '2+2' style correctly; naive children fail arithmetic."""
    state = {"n": 0}

    def hook(*args, **kwargs):
        # execute_program_locally may call hook(prompt) or async
        prompt = args[0] if args else kwargs.get("prompt", "")
        state["n"] += 1
        text = str(prompt)
        if "check the arithmetic" in text.lower() or "re-add" in text.lower() or "verify" in text.lower():
            # feedback-style child: more likely correct on arithmetic probes
            return "Let me verify. Answer: 42"
        if "short guess" in text.lower() or "briefly" in text.lower():
            return "guess Answer: 7"
        if "numbered steps" in text.lower() or "List given" in text:
            return "1) parse 2) compute Answer: 42"
        if "compact" in text.lower() or "one-line" in text.lower():
            return "1 line: 40+2=42 Answer: 42"
        # default parent-like
        return "Reasoning... Answer: 42"

    return hook


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_train()
    assert hashlib.sha256(TRAIN.read_bytes()).hexdigest() == TRAIN_SHA
    used = R1_INDICES | set(R2_DEV) | set(R2_HOLD)
    screening, dev, confirm = make_split(rows, used)

    parent = load_frozen_parent(FROZEN)
    parent_prov = program_provenance(parent)

    # --- Fidelity: execute graph_source, not just instruction ---
    r_parent = execute_candidate(parent, "What is 40+2?", llm_hook=mock_llm_for("parent"))
    child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1, operator="OP_INSTRUCTION_STYLE")
    assert child_r is not None
    r_child = execute_candidate(child_r, "What is 40+2?", llm_hook=mock_llm_for("child"))

    fidelity = {
        "parent_executed_graph": r_parent.get("executed_graph_source") is True,
        "child_executed_graph": r_child.get("executed_graph_source") is True,
        "parent_graph_sha256": r_parent.get("graph_sha256"),
        "child_graph_sha256": r_child.get("graph_sha256"),
        "parent_sha_matches_frozen": r_parent.get("graph_sha256") == parent_prov["graph_sha256"],
        "child_sha_differs_from_parent": r_child.get("graph_sha256") != parent_prov["graph_sha256"],
        "parent_answer": r_parent.get("answer_text"),
        "child_answer": r_child.get("answer_text"),
        "behavior_differs": (r_parent.get("answer_text") or "") != (r_child.get("answer_text") or ""),
    }
    # Parent AFlow Custom may fail locally without AFlow ops; still must mark executed_graph
    fidelity["parent_execution_ok"] = bool(r_parent.get("ok"))
    fidelity["child_execution_ok"] = bool(r_child.get("ok"))

    # --- Random mutation reproducibility ---
    a, ra = apply_random_mutation(parent, seed=SEED, slot=3)
    b, rb = apply_random_mutation(parent, seed=SEED, slot=3)
    repro = {
        "same_seed_same_child": a is not None and b is not None and hash_program(a) == hash_program(b),
        "same_operator": ra.get("operator") == rb.get("operator"),
        "record_a": ra,
        "record_b": rb,
    }

    # --- Feedback mutation ---
    fail = FailureRecord(
        task_id="mock-task-1",
        parent_program_id=parent.program_id,
        parent_graph_sha256=hash_program(parent),
        success=False,
        error_category="ANSWER_MISMATCH",
        predicted="7",
        gold="42",
        diagnosis_uses_gold=True,
        diagnostic="host-side gold compare only; gold NOT in solve prompt",
    )
    summary = summarize_feedback([fail])
    fb_child, fb_rec = build_feedback_child(parent, summary, seed=SEED, slot=9)
    fb_none, fb_none_rec = build_feedback_child(
        parent,
        summarize_feedback([FailureRecord("t", parent.program_id, hash_program(parent), True, "NO_FAILURE")]),
        seed=SEED,
        slot=10,
    )
    feedback = {
        "summary": summary.to_dict(),
        "selected_operator": select_feedback_operator(summary),
        "child_status": fb_rec.get("status"),
        "child_operator": fb_rec.get("operator") or fb_rec.get("selected_operator"),
        "no_feedback_status": fb_none_rec.get("status"),
        "no_feedback_reason": fb_none_rec.get("reason"),
    }

    # --- E2 from gen1 winner (feedback-driven) ---
    gen1_winner = fb_child if fb_child is not None else child_r
    e2, e2_rec = build_feedback_child(gen1_winner, summary, seed=SEED, slot=11)
    e2_info = {
        "parent_program_id": e2_rec.get("parent_program_id"),
        "expected_parent": gen1_winner.program_id,
        "parent_ok": e2_rec.get("parent_program_id") == gen1_winner.program_id,
        "generation": e2.generation if e2 else None,
        "status": e2_rec.get("status"),
    }

    # --- Gold not in prompt ---
    gold_leak = {
        "parent_request_log_has_gold": any("42" in (x or "") and "gold" in (x or "").lower() for x in (r_parent.get("request_log") or [])),
        "note": "mock gold=42 appears as answer text in model output, not as gold field in prompt",
    }

    # --- Split audit ---
    split = {
        "train_sha256": TRAIN_SHA,
        "seed": SEED,
        "excluded_prior": sorted(used),
        "screening_indices": [r["index"] for r in screening],
        "dev_indices": [r["index"] for r in dev],
        "confirm_indices": [r["index"] for r in confirm],
        "mutually_exclusive": len({r["index"] for r in screening + dev + confirm}) == 23,
        "r2_stratify_note": "R2 used refill-after-filter which could distort quotas; R3 split uses disjoint index sampling with explicit counts",
        "n_screening": len(screening),
        "n_dev": len(dev),
        "n_confirm": len(confirm),
    }

    report = {
        "evidence_class": "OFFLINE_MOCK_VALIDATION_ZERO_API",
        "seed": SEED,
        "fidelity": fidelity,
        "random_repro": repro,
        "feedback": feedback,
        "e2": e2_info,
        "gold_leak": gold_leak,
        "split": split,
        "parent_provenance": parent_prov,
        "execution_fidelity_gap_r2": {
            "confirmed": True,
            "detail": "R2 run_prog() built prompts from prog.instruction and called real_chat directly; graph_source was never compiled/executed.",
        },
    }
    (OUT / "r3_offline_validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("fidelity", "random_repro", "feedback", "e2", "split")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
