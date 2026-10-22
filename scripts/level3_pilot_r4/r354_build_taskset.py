"""R3.5.4: freeze independent tasksets for mechanism isolation. Offline."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
OUT = ROOT / "results/level3_pilot_r4_micro_r354"
SEED = 20260606

# All historically evaluated/reserved indices (R1-R3.5.3)
USED = set(range(0, 8))
# load all previous tasksets for precise exclusion
for rel, keys in [
    ("results/level3_pilot_r4_micro_r34/taskset.json", ("calibration", "dev", "confirm")),
    ("results/level3_pilot_r4_micro_r35/taskset_r35.json", ("dev", "confirm")),
]:
    p = ROOT / rel
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        for k in keys:
            if k in data:
                USED |= set(data[k].get("indices") or [])
# R3.3 live used these
USED |= {4336, 2201, 2495, 5648, 4346, 3098, 6031, 4459, 6404, 2184, 1856, 856, 4627}

N_CALIB, N_DEV, N_CONFIRM = 10, 15, 30


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
                         "question_norm_sha256": qh})

    rng = random.Random(SEED)
    idxs = list(range(len(rows)))
    rng.shuffle(idxs)
    calib = [rows[i] for i in idxs[:N_CALIB]]
    dev = [rows[i] for i in idxs[N_CALIB:N_CALIB + N_DEV]]
    conf = [rows[i] for i in idxs[N_CALIB + N_DEV:N_CALIB + N_DEV + N_CONFIRM]]
    assert len(calib) == N_CALIB and len(dev) == N_DEV and len(conf) == N_CONFIRM
    sets = [set(r["index"] for r in x) for x in (calib, dev, conf)]
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])
    assert not (sets[0] | sets[1] | sets[2]) & USED

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
        "protocol": "MICRO-R3.5.4-MECHANISM-ISOLATION-v1",
        "seed": SEED,
        "train_sha256": TRAIN_SHA,
        "n_calib": N_CALIB,
        "n_dev": N_DEV,
        "n_confirm": N_CONFIRM,
        "calib_task_set_sha256": sha_block(calib),
        "dev_task_set_sha256": sha_block(dev),
        "confirm_task_set_sha256": sha_block(conf),
        "used_indices_excluded": sorted(USED),
        "dedup": "normalized question sha256 + gold",
        "confirm_used_for_selection": False,
        "frozen_before_candidates": True,
        "arms": ["B", "A", "O"],
        "mechanism_contrast": {
            "A_vs_B": "append feedback to non-empty base strategy",
            "O_vs_B": "replace base strategy with same feedback text",
            "A_vs_O": "strategy-preservation mechanism (primary)",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "taskset_r354.json").write_text(json.dumps({
        "calibration": block(calib, "calibration"),
        "dev": block(dev, "development"),
        "confirm": block(conf, "confirmation"),
    }, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "taskset_r354_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(man, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
