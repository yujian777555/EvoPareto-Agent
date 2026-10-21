"""Build R3.4 harder task sets (calibration + frozen confirmation).

Offline. No API. Writes freeze artifacts under results/level3_pilot_r4_micro_r34/.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
OUT = ROOT / "results/level3_pilot_r4_micro_r34"
SEED = 20260604

# Historical usage (exclude content, not just ids)
USED_INDICES = set(range(0, 8)) | {
    6245, 499, 6996, 4900, 2518,
    3741, 475, 5516, 2354, 1139, 1066, 3324, 7193,
    4336, 2201, 2495, 5648, 4346,
    3098, 6031, 4459, 6404, 2184, 1856, 856, 4627,
    # reserved screening from R3 (not scored but avoid reuse)
    5895, 1540, 6485, 7068, 7166, 3011, 7396, 6596, 1900, 6752,
}

N_CALIB = 12
N_CONFIRM = 30


def complexity_score(q: str) -> int:
    """Heuristic hardness (NOT true difficulty): counts relational density."""
    s = 0
    ql = q.lower()
    s += len(re.findall(r"\d+", q))
    for w in ("more than", "less than", "times", "twice", "thrice", "half", "each", "every", "total", "altogether", "left", "remaining", "combined", "per ", "percent", "fraction"):
        if w in ql:
            s += 2
    # multi-entity mentions
    s += min(6, len(re.findall(r"\b(and|while|if|after|before|then)\b", ql)))
    # longer questions slightly harder
    s += min(10, len(q.split()) // 8)
    return s


def main() -> int:
    assert hashlib.sha256(TRAIN.read_bytes()).hexdigest() == TRAIN_SHA
    rows = []
    seen_q = set()
    seen_gold_q = set()
    with TRAIN.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
            gold = " ".join(gold.split())
            qn = " ".join(o["question"].split())
            # content-hash dedup
            qh = hashlib.sha256(qn.encode("utf-8")).hexdigest()
            key = (qh, gold)
            if key in seen_gold_q:
                continue
            seen_gold_q.add(key)
            if i in USED_INDICES:
                continue
            rows.append({
                "index": i,
                "question": o["question"],
                "answer_raw": ans,
                "gold": gold,
                "sol_len": len(ans.split()),
                "complexity": complexity_score(o["question"]),
                "question_norm_sha256": qh,
            })

    rows.sort(key=lambda r: (-r["complexity"], r["index"]))
    # Calibration: top complexity slice (hard for Parent to hit ceiling)
    calib = rows[:N_CALIB]
    rest = rows[N_CALIB:]
    # Confirmation: next hard 30, distinct from calib
    confirm = rest[:N_CONFIRM]
    # Development from remaining hard-ish (for selection if needed)
    dev = rest[N_CONFIRM:N_CONFIRM + 5]

    assert not ({r["index"] for r in calib} & {r["index"] for r in confirm})
    assert not ({r["index"] for r in calib} & {r["index"] for r in dev})
    assert not ({r["index"] for r in confirm} & {r["index"] for r in dev})
    assert not ({r["index"] for r in calib + confirm + dev} & USED_INDICES)

    def freeze_block(items, role):
        return {
            "role": role,
            "n": len(items),
            "indices": [r["index"] for r in items],
            "tasks": [{
                "task_id": f"gsm8k-train-{r['index']:04d}",
                "question": r["question"],
                "gold_answer": r["gold"],
                "question_norm_sha256": r["question_norm_sha256"],
                "complexity_heuristic": r["complexity"],
                "sol_len": r["sol_len"],
            } for r in items],
        }

    def sha_tasks(items):
        blob = json.dumps(
            [(f"gsm8k-train-{r['index']:04d}", " ".join(r["question"].split()), r["gold"]) for r in items],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    manifest = {
        "evidence_class": "OFFLINE_TASKSET_FREEZE",
        "protocol": "MICRO-R3.4-HARDSET",
        "seed": SEED,
        "train_sha256": TRAIN_SHA,
        "used_indices_excluded": sorted(USED_INDICES),
        "dedup": "normalized question sha256 + gold",
        "complexity_rule": "heuristic: digit count + relational keywords + connectives + length/8; NOT true difficulty",
        "calibration_task_set_sha256": sha_tasks(calib),
        "confirm_task_set_sha256": sha_tasks(confirm),
        "dev_task_set_sha256": sha_tasks(dev),
        "n_calib": len(calib),
        "n_confirm": len(confirm),
        "n_dev": len(dev),
        "selection_rule": "dev accuracy max; tie -> fixed order R before F",
        "e2_rule": "from gen-1 winner FailureRecords only; else NOT_GENERATED_NO_FAILURE",
        "confirm_used_for_selection": False,
        "frozen_before_candidate_gen": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "taskset.json").write_text(json.dumps({
        "calibration": freeze_block(calib, "calibration"),
        "dev": freeze_block(dev, "development"),
        "confirm": freeze_block(confirm, "confirmation"),
    }, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "taskset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    print("calib complexity", [r["complexity"] for r in calib])
    print("confirm complexity range", min(r["complexity"] for r in confirm), max(r["complexity"] for r in confirm))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
