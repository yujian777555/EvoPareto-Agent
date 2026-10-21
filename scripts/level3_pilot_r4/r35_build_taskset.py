"""R3.5: freeze new independent dev/confirm tasksets (train only). Offline."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
OUT = ROOT / "results/level3_pilot_r4_micro_r35"
SEED = 20260605

# All historical scored/reserved indices (R1,R2,R3.3,R3.4)
USED = set(range(0, 8)) | {
    6245, 499, 6996, 4900, 2518, 3741, 475, 5516, 2354, 1139, 1066, 3324, 7193,
    4336, 2201, 2495, 5648, 4346, 3098, 6031, 4459, 6404, 2184, 1856, 856, 4627,
    5895, 1540, 6485, 7068, 7166, 3011, 7396, 6596, 1900, 6752,
}
# R3.4 live used calib+dev+confirm — load from freeze to exclude precisely
r34 = json.loads((ROOT / "results/level3_pilot_r4_micro_r34/taskset.json").read_text(encoding="utf-8"))
for role in ("calibration", "dev", "confirm"):
    USED |= set(r34[role]["indices"])

N_DEV, N_CONFIRM = 20, 30


def main() -> int:
    assert hashlib.sha256(TRAIN.read_bytes()).hexdigest() == TRAIN_SHA
    rows = []
    seen = set()
    with TRAIN.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = " ".join((ans.rsplit("####", 1)[-1] if "####" in ans else ans).strip().split())
            qn = " ".join(o["question"].split())
            qh = hashlib.sha256(qn.encode("utf-8")).hexdigest()
            key = (qh, gold)
            if key in seen:
                continue
            seen.add(key)
            if i in USED:
                continue
            rows.append({"index": i, "question": o["question"], "gold": gold,
                         "answer_raw": ans, "question_norm_sha256": qh})

    rng = random.Random(SEED)
    idxs = list(range(len(rows)))
    rng.shuffle(idxs)
    dev = [rows[i] for i in idxs[:N_DEV]]
    conf = [rows[i] for i in idxs[N_DEV:N_DEV + N_CONFIRM]]
    assert len(dev) == N_DEV and len(conf) == N_CONFIRM
    di, ci = {r["index"] for r in dev}, {r["index"] for r in conf}
    assert not di & ci
    assert not (di | ci) & USED

    def sha_block(items):
        blob = json.dumps(
            [(f"gsm8k-train-{r['index']:04d}", " ".join(r["question"].split()), r["gold"]) for r in items],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def block(items, role):
        return {
            "role": role,
            "n": len(items),
            "indices": [r["index"] for r in items],
            "tasks": [{
                "task_id": f"gsm8k-train-{r['index']:04d}",
                "question": r["question"],
                "gold_answer": r["gold"],
                "question_norm_sha256": r["question_norm_sha256"],
            } for r in items],
        }

    man = {
        "evidence_class": "OFFLINE_TASKSET_FREEZE",
        "protocol": "MICRO-R3.5",
        "seed": SEED,
        "train_sha256": TRAIN_SHA,
        "n_dev": N_DEV,
        "n_confirm": N_CONFIRM,
        "dev_task_set_sha256": sha_block(dev),
        "confirm_task_set_sha256": sha_block(conf),
        "used_indices_excluded": sorted(USED),
        "r34_confirm_reuse": "diagnostic only; NOT new confirmation",
        "dedup": "normalized question sha256 + gold",
        "confirm_used_for_selection": False,
        "frozen_before_candidates": True,
    }
    (OUT / "taskset_r35.json").write_text(json.dumps({"dev": block(dev, "development"), "confirm": block(conf, "confirmation")}, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "taskset_r35_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(man, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
