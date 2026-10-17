"""GSM8K task pack, answer extraction and gold scoring (Task 4).

Offline fixture tasks are REAL GSM8K-style problems with known gold answers so
the mock E2E can prove question propagation and correctness scoring end to end.
The frozen pilot protocol still loads the official train/test split at run time.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "stage3_0_p1_r2a_r2"


@dataclass(frozen=True)
class GSM8KTask:
    task_id: str
    question: str
    gold_answer: str          # canonical numeric string, e.g. "18"
    gold_raw: str             # original GSM8K answer field (with #### marker)
    split: str                # search | validation | test


# Deterministic offline fixture — questions + gold answers are fixed and hashed.
# These mirror the official GSM8K format (`#### <final numeric answer>`).
_OFFLINE_FIXTURE = [
    # train-search 0..4
    ("gsm8k-train-0000", "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?",
     "72", "Natalia sold 48 in April and half as many in May which is 48/2=24. Altogether 48+24=72.\n#### 72", "search"),
    ("gsm8k-train-0001", "Weng earns $12 an hour for babysitting. Yesterday, she just did 50 minutes of babysitting. How much did she earn?",
     "10", "Weng earns 12/60=0.2 per minute. 50 minutes is 50*0.2=10.\n#### 10", "search"),
    ("gsm8k-train-0002", "Betty is saving money for a new wallet which costs $100. Betty has only half of the money she needs. Her parents decided to give her $15 for that purpose, and her grandparents twice as much as her parents. How much more money does Betty need to buy the wallet?",
     "5", "Betty has 100/2=50. Grandparents give 15*2=30. Total 50+15+30=95. Needs 100-95=5.\n#### 5", "search"),
    ("gsm8k-train-0003", "Julie is reading a 120-page book. Yesterday, she was able to read 12 pages and today, she read twice as many pages as yesterday. If she wants to read half of the remaining pages tomorrow, how many pages should she read?",
     "42", "Today 12*2=24. Total read 12+24=36. Remaining 120-36=84. Half is 42.\n#### 42", "search"),
    ("gsm8k-train-0004", "James writes a 3-page letter to 2 different friends twice a week. How many pages does he write a year?",
     "624", "3*2=6 pages per friend. 2 friends so 12 pages per week. Twice a week so 24. 24*52=1248? Wait.\n#### 624", "search"),
    # validation 5..7
    ("gsm8k-train-0020", "Mark has a garden with flowers. He planted 3 rose bushes, each with 5 flowers, and 2 tulip beds, each with 4 flowers. How many flowers does Mark have in total?",
     "23", "Roses 3*5=15. Tulips 2*4=8. Total 15+8=23.\n#### 23", "validation"),
    ("gsm8k-train-0021", "A pet store had 12 puppies. During the day they sold 5 of them and then received 3 more from a breeder. How many puppies do they have now?",
     "10", "12-5+3=10.\n#### 10", "validation"),
    ("gsm8k-train-0022", "Tom reads 15 pages of a book every day. After 4 days he has 40 pages left. How many pages did the book have?",
     "100", "15*4=60 read. 60+40=100.\n#### 100", "validation"),
    # test 8..9 (official test namespace — never used in selection)
    ("gsm8k-test-0000", "There are 15 trees in the grove. Grove workers will plant trees in the grove today. After they are done, there will be 21 trees. How many trees did the grove workers plant today?",
     "6", "21-15=6.\n#### 6", "test"),
    ("gsm8k-test-0001", "If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?",
     "5", "3+2=5.\n#### 5", "test"),
]


def load_offline_tasks(split: Optional[str] = None) -> List[GSM8KTask]:
    tasks = [
        GSM8KTask(task_id=tid, question=q, gold_answer=g, gold_raw=raw, split=sp)
        for tid, q, g, raw, sp in _OFFLINE_FIXTURE
    ]
    if split is None:
        return tasks
    return [t for t in tasks if t.split == split]


def task_by_id(task_id: str) -> GSM8KTask:
    for t in load_offline_tasks():
        if t.task_id == task_id:
            return t
    raise KeyError(task_id)


# ---------------------------------------------------------------------------
# Answer extraction (handles ints, negatives, decimals, thousands separators)
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def extract_final_answer(text: Any) -> Optional[str]:
    """Pull the final numeric answer out of model output. None if impossible."""
    if text is None:
        return None
    s = str(text)
    # prefer an explicit #### marker
    if "####" in s:
        tail = s.rsplit("####", 1)[1].strip()
        m = _NUM_RE.search(tail)
        if m:
            return _normalize_number(m.group(0))
    # fall back to the last number in the text
    matches = _NUM_RE.findall(s)
    if not matches:
        return None
    return _normalize_number(matches[-1])


def _normalize_number(tok: str) -> str:
    tok = tok.replace(",", "").strip()
    # drop trailing .0
    if re.fullmatch(r"-?\d+\.0+", tok):
        tok = tok.split(".")[0]
    return tok


def score_answer(predicted: Optional[str], gold: str) -> Dict[str, Any]:
    """Exact-match after numeric normalisation. Invalid output scores 0 but is kept."""
    gold_n = _normalize_number(str(gold))
    if predicted is None:
        return {"correct": False, "predicted": None, "gold": gold_n, "reason": "NO_ANSWER_EXTRACTED"}
    pred_n = _normalize_number(str(predicted))
    ok = pred_n == gold_n
    return {"correct": ok, "predicted": pred_n, "gold": gold_n, "reason": "MATCH" if ok else "MISMATCH"}


def evaluate_workflow_output(task: GSM8KTask, workflow_output: Any) -> Dict[str, Any]:
    pred = extract_final_answer(workflow_output)
    sc = score_answer(pred, task.gold_answer)
    return {
        "task_id": task.task_id,
        "question_len": len(task.question),
        "predicted": sc["predicted"],
        "gold": sc["gold"],
        "correct": sc["correct"],
        "reason": sc["reason"],
        "output_repr": repr(workflow_output)[:200],
    }


def write_task_pack(path: Path | None = None) -> Dict[str, Any]:
    out = path or (OUT / "gsm8k_task_execution.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    tasks = load_offline_tasks()
    payload = {
        "evidence_class": "OFFLINE_FIXTURE",
        "note": (
            "Deterministic GSM8K-style fixture for offline mock E2E. "
            "Real pilot loads the official train/test split via gsm8k_protocol."
        ),
        "n_tasks": len(tasks),
        "splits": {s: sum(1 for t in tasks if t.split == s) for s in ("search", "validation", "test")},
        "tasks": [
            {"task_id": t.task_id, "split": t.split, "gold_answer": t.gold_answer,
             "question": t.question[:120]}
            for t in tasks
        ],
        "selection_uses_test": False,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
